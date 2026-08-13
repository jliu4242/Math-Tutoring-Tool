-- Phase 1 — ingestion job tracking (ARCHITECTURE.md section 25).
--
-- Ingestion runs in the background (section 28), so the job state has to be durable
-- and the UI has to be able to poll it to know when the textbook is ready
-- (section 39).

create table public.ingestion_runs (
    id            uuid                    primary key default gen_random_uuid(),
    textbook_id   uuid                    not null references public.textbooks (id) on delete cascade,
    status        public.ingestion_status not null default 'queued',
    current_stage public.ingestion_stage  not null default 'upload',
    progress      jsonb                   not null default '{}'::jsonb,
    error         text,
    started_at    timestamptz,
    completed_at  timestamptz,
    updated_at    timestamptz             not null default now()
);

create index ingestion_runs_textbook_id_idx
    on public.ingestion_runs (textbook_id);

-- Worker picks up queued/processing runs.
create index ingestion_runs_status_idx
    on public.ingestion_runs (status);

comment on column public.ingestion_runs.progress is
    'Per-stage progress, keyed by ingestion_stage, so the UI can render the stage '
    'checklist in ARCHITECTURE.md section 25.';

-- Keep updated_at honest without every writer having to remember it.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger ingestion_runs_touch_updated_at
    before update on public.ingestion_runs
    for each row
    execute function public.touch_updated_at();
