-- Phase 1 — textbook core (ARCHITECTURE.md section 17).
--
-- Source data. Per section 4 the PDF, its pages and their raw text are immutable
-- source; everything derived from them lives in later migrations.

-- ARCHITECTURE.md section 17 — Textbooks
create table public.textbooks (
    id          uuid primary key default gen_random_uuid(),
    title       text        not null,
    edition     text,
    publisher   text,
    subject     text,
    grade_band  text,
    created_at  timestamptz not null default now()
);

-- ARCHITECTURE.md section 17 — Sources
-- The original PDF stays in object storage (section 16); storage_path points at it.
create table public.textbook_sources (
    id           uuid primary key default gen_random_uuid(),
    textbook_id  uuid        not null references public.textbooks (id) on delete cascade,
    file_hash    text        not null,
    storage_path text        not null,
    page_count   integer     not null check (page_count >= 0),
    uploaded_at  timestamptz not null default now(),

    constraint textbook_sources_file_hash_key unique (file_hash)
);

create index textbook_sources_textbook_id_idx
    on public.textbook_sources (textbook_id);

-- ARCHITECTURE.md section 17 — Pages
create table public.textbook_pages (
    id                uuid              primary key default gen_random_uuid(),
    source_id         uuid              not null references public.textbook_sources (id) on delete cascade,
    page_number       integer           not null check (page_number >= 1),
    raw_text          text,
    extraction_status public.extraction_status not null default 'pending',
    created_at        timestamptz       not null default now(),

    constraint textbook_pages_source_page_key unique (source_id, page_number)
);

create index textbook_pages_source_id_idx
    on public.textbook_pages (source_id);

-- ARCHITECTURE.md section 17 — Chapters
-- `number` is text: chapter labels are not reliably integers (e.g. "3A", "Appendix B").
create table public.chapters (
    id          uuid    primary key default gen_random_uuid(),
    textbook_id uuid    not null references public.textbooks (id) on delete cascade,
    number      text,
    title       text    not null,
    page_start  integer check (page_start >= 1),
    page_end    integer check (page_end >= 1),
    ordinal     integer not null,

    constraint chapters_textbook_ordinal_key unique (textbook_id, ordinal),
    constraint chapters_page_range_check check (page_end is null or page_start is null or page_end >= page_start)
);

create index chapters_textbook_id_idx
    on public.chapters (textbook_id);

-- ARCHITECTURE.md section 17 — Sections
-- parent_section_id allows nested sections/subsections.
create table public.sections (
    id                uuid    primary key default gen_random_uuid(),
    chapter_id        uuid    not null references public.chapters (id) on delete cascade,
    parent_section_id uuid    references public.sections (id) on delete cascade,
    title             text    not null,
    ordinal           integer not null,
    page_start        integer check (page_start >= 1),
    page_end          integer check (page_end >= 1),
    content           text,

    constraint sections_not_own_parent_check check (parent_section_id is null or parent_section_id <> id),
    constraint sections_page_range_check check (page_end is null or page_start is null or page_end >= page_start)
);

create index sections_chapter_id_idx
    on public.sections (chapter_id);

create index sections_parent_section_id_idx
    on public.sections (parent_section_id);
