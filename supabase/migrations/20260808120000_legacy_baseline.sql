-- Baseline: the tables the application already used before Phase 1 ingestion work.
--
-- These were created ad hoc against the hosted Supabase project and were never
-- captured as migrations. This file reproduces that pre-existing state so a clean
-- local database converges with the hosted one.
--
-- Against the hosted project, mark this migration as already applied instead of
-- running it:  supabase migration repair --status applied 20260808120000

create table if not exists public.problems (
    id           uuid primary key default gen_random_uuid(),
    source       text        not null default 'generated',
    topic        text        not null,
    grade_level  text        not null,
    difficulty   text        not null default 'medium',
    body         text        not null,
    solution     text        not null default '',
    created_at   timestamptz not null default now()
);

create table if not exists public.lesson_plans (
    id              uuid primary key default gen_random_uuid(),
    topic           text        not null,
    grade_level     text        not null,
    duration_min    integer     not null default 60,
    objectives      text        not null default '',
    warm_up         text        not null default '',
    explanation     text        not null default '',
    examples        text        not null default '',
    practice        text        not null default '',
    assessment      text        not null default '',
    marketing_copy  text        not null default '',
    created_at      timestamptz not null default now()
);

create table if not exists public.grading_sessions (
    id             uuid primary key default gen_random_uuid(),
    problem_id     uuid        not null references public.problems (id) on delete cascade,
    student_label  text        not null default 'Student A',
    work_input     text        not null,
    diagnosis      jsonb       not null default '{}'::jsonb,
    follow_up_ids  jsonb       not null default '[]'::jsonb,
    created_at     timestamptz not null default now()
);

create index if not exists grading_sessions_problem_id_idx
    on public.grading_sessions (problem_id);
