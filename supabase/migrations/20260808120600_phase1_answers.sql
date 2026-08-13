-- Phase 1 — answers and solutions
-- (ARCHITECTURE.md sections 23, 24).
--
-- Answers and solutions are stored separately because they come from a different
-- part of the textbook and mean different things (section 13): an answer key entry
-- is not a worked solution. A problem with an answer but no printed solution has a
-- problem_answers row and no problem_solutions row — never a guessed solution.

-- ARCHITECTURE.md section 23 — Answers
--
-- matching_method and confidence are both NOT NULL so the audit trail exists from
-- the first write rather than being backfilled (sections 23 and 27).
create table public.problem_answers (
    id                 uuid                    primary key default gen_random_uuid(),
    problem_id         uuid                    not null references public.problems (id) on delete cascade,
    answer_text        text                    not null,
    answer_source_page integer                 check (answer_source_page >= 1),
    answer_source_ref  jsonb,
    matching_method    public.matching_method  not null,
    confidence         double precision        not null check (confidence >= 0 and confidence <= 1),
    created_at         timestamptz             not null default now()
);

create index problem_answers_problem_id_idx
    on public.problem_answers (problem_id);

-- Supports surfacing uncertain matches for review (section 27).
create index problem_answers_confidence_idx
    on public.problem_answers (confidence);

create index problem_answers_matching_method_idx
    on public.problem_answers (matching_method);

-- ARCHITECTURE.md section 24 — Solutions
create table public.problem_solutions (
    id            uuid        primary key default gen_random_uuid(),
    problem_id    uuid        not null references public.problems (id) on delete cascade,
    solution_text text        not null,
    source_page   integer     check (source_page >= 1),
    source_ref    jsonb,
    created_at    timestamptz not null default now()
);

create index problem_solutions_problem_id_idx
    on public.problem_solutions (problem_id);
