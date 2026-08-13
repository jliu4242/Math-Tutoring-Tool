-- Free the `problems` name for the Phase 1 ingestion schema (ARCHITECTURE.md section 19).
--
-- The pre-existing `problems` table holds AI-generated practice problems, which is a
-- different concept from a textbook problem extracted during ingestion. It is renamed
-- to `generated_problems`; the ingestion table takes the `problems` name in a later
-- migration.

alter table public.problems rename to generated_problems;

-- Keep constraint/index names consistent with the new table name.
alter index if exists problems_pkey rename to generated_problems_pkey;

alter table public.grading_sessions
    rename constraint grading_sessions_problem_id_fkey
    to grading_sessions_generated_problem_id_fkey;
