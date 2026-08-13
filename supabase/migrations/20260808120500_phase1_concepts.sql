-- Phase 1 — concepts and their associations
-- (ARCHITECTURE.md sections 21, 22).
--
-- Concepts are canonical and textbook-independent, so multiple textbooks can
-- eventually reference the same concept (section 21).

-- ARCHITECTURE.md section 21 — Concepts
create table public.concepts (
    id                uuid        primary key default gen_random_uuid(),
    slug              text        not null,
    canonical_name    text        not null,
    description       text,
    grade_band        text,
    parent_concept_id uuid        references public.concepts (id) on delete set null,
    created_at        timestamptz not null default now(),

    constraint concepts_slug_key unique (slug),
    constraint concepts_not_own_parent_check check (parent_concept_id is null or parent_concept_id <> id)
);

create index concepts_parent_concept_id_idx
    on public.concepts (parent_concept_id);

-- ARCHITECTURE.md section 21 — section_concepts
-- local_name records what this textbook calls the concept, which may differ from
-- the canonical name.
create table public.section_concepts (
    section_id uuid    not null references public.sections (id) on delete cascade,
    concept_id uuid    not null references public.concepts (id) on delete cascade,
    local_name text,
    ordinal    integer,

    primary key (section_id, concept_id)
);

create index section_concepts_concept_id_idx
    on public.section_concepts (concept_id);

-- ARCHITECTURE.md section 22 — problem_concepts
--
-- confidence is required: section 27 is explicit that a concept assignment must not
-- silently become an unquestioned fact.
--
-- NOTE: the spec names relationship_type but does not enumerate its values, so it is
-- left as free text rather than guessing an enum.
create table public.problem_concepts (
    problem_id        uuid             not null references public.problems (id) on delete cascade,
    concept_id        uuid             not null references public.concepts (id) on delete cascade,
    relationship_type text,
    confidence        double precision not null check (confidence >= 0 and confidence <= 1),

    primary key (problem_id, concept_id)
);

create index problem_concepts_concept_id_idx
    on public.problem_concepts (concept_id);

-- Supports "show me the low-confidence concept assignments" review queries (section 27).
create index problem_concepts_confidence_idx
    on public.problem_concepts (confidence);
