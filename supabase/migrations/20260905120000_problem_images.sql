-- MinerU ingestion swap -- problem images (ARCHITECTURE.md section 6, section 19).
--
-- Figures MinerU detects (graphs, diagrams) were being recorded in
-- textbook_pages.images (mineru_extraction.ImageBlock) but never persisted as
-- actual image bytes anywhere, and never linked to the problem they illustrate --
-- a real gap for geometry/graphing problems whose text alone doesn't carry the
-- question ("the graph of this problem is like this, find ..."). This migration adds
-- the storage + linking half of that.
--
-- Scoped to problems only, not a generic polymorphic images table: worked examples
-- and general content_blocks can also contain figures, but linking those is a
-- separate, not-yet-requested extension of this table's shape.
--
-- Private bucket, not public: nothing here is ever served from a bare storage URL.
-- Display always goes through a signed URL minted on request
-- (ingestion/persistence.py's create_signed_image_url) -- see routers/problems.py
-- for the endpoint that does that minting for a client.
insert into storage.buckets (id, name, public)
values ('textbook-images', 'textbook-images', false)
on conflict (id) do nothing;

create table public.problem_images (
    id           uuid        primary key default gen_random_uuid(),
    problem_id   uuid        not null references public.problems (id) on delete cascade,
    storage_path text        not null,
    ordinal      integer     not null,
    caption      text,
    source_ref   jsonb,
    created_at   timestamptz not null default now(),

    constraint problem_images_problem_id_ordinal_key unique (problem_id, ordinal)
);

create index problem_images_problem_id_idx
    on public.problem_images (problem_id, ordinal);
