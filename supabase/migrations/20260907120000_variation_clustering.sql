-- Variation clustering (ARCHITECTURE.md section 10.2, section 22).
--
-- Step 4c's draft output needs two things the original problem_concepts columns
-- (problem_id, concept_id, relationship_type, confidence) cannot express: which
-- variation a problem was grouped into, and whether it was chosen to represent
-- that variation. See ARCHITECTURE.md section 22's "variation_key and
-- is_representative" discussion for why these are the minimum needed.

alter table public.problem_concepts
    add column variation_key     text,
    add column is_representative boolean not null default false;

-- At most one representative per variation, enforced in the database rather than
-- by convention (ARCHITECTURE.md section 22).
create unique index problem_concepts_one_representative_per_variation
    on public.problem_concepts (concept_id, variation_key)
    where is_representative;

-- ARCHITECTURE.md section 25 -- the stage this migration's columns support.
alter type public.ingestion_stage add value 'variation_clustering' after 'concept_extraction';
