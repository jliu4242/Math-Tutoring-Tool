-- Phase 1 — content blocks, problems, worked examples
-- (ARCHITECTURE.md sections 18, 19, 20).
--
-- source_ref is jsonb throughout: section 6 asks for source coordinates where useful
-- and section 15 requires every extracted object to link back to the PDF well enough
-- to answer "why does the system think this is Problem 17?".

-- ARCHITECTURE.md section 18 — Textbook content
create table public.content_blocks (
    id         uuid              primary key default gen_random_uuid(),
    section_id uuid              not null references public.sections (id) on delete cascade,
    block_type public.block_type not null,
    ordinal    integer           not null,
    page_start integer           check (page_start >= 1),
    page_end   integer           check (page_end >= 1),
    content    text              not null,
    source_ref jsonb,

    constraint content_blocks_page_range_check check (page_end is null or page_start is null or page_end >= page_start)
);

create index content_blocks_section_id_idx
    on public.content_blocks (section_id, ordinal);

-- ARCHITECTURE.md section 19 — Problems
--
-- chapter_id and section_id are nullable so the pipeline can record a problem it
-- extracted but has not yet placed. Section 26 makes "problems belong to a
-- section/chapter" a validation check, not a schema constraint, so that an
-- incomplete run is caught and reported rather than failing on insert.
create table public.problems (
    id             uuid        primary key default gen_random_uuid(),
    textbook_id    uuid        not null references public.textbooks (id) on delete cascade,
    chapter_id     uuid        references public.chapters (id) on delete set null,
    section_id     uuid        references public.sections (id) on delete set null,
    source_ref     jsonb,
    page_number    integer     check (page_number >= 1),
    problem_number text,
    body_latex     text,
    body_plain     text        not null,
    ordinal        integer     not null,
    created_at     timestamptz not null default now()
);

create index problems_textbook_id_idx on public.problems (textbook_id);
create index problems_chapter_id_idx  on public.problems (chapter_id);
create index problems_section_id_idx  on public.problems (section_id, ordinal);

-- Answer matching (section 14) looks problems up by chapter + printed number.
create index problems_chapter_number_idx
    on public.problems (chapter_id, problem_number);

-- ARCHITECTURE.md section 20 — Worked Examples
-- Kept separate from problems so later features can tell textbook problems from
-- worked examples without re-parsing the PDF (section 11).
create table public.worked_examples (
    id             uuid        primary key default gen_random_uuid(),
    textbook_id    uuid        not null references public.textbooks (id) on delete cascade,
    chapter_id     uuid        references public.chapters (id) on delete set null,
    section_id     uuid        references public.sections (id) on delete set null,
    source_ref     jsonb,
    page_number    integer     check (page_number >= 1),
    example_number text,
    problem_text   text        not null,
    solution_text  text,
    ordinal        integer     not null,
    created_at     timestamptz not null default now()
);

create index worked_examples_textbook_id_idx on public.worked_examples (textbook_id);
create index worked_examples_chapter_id_idx  on public.worked_examples (chapter_id);
create index worked_examples_section_id_idx  on public.worked_examples (section_id, ordinal);
