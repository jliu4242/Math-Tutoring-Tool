"""Phase 1 ingestion stages (ARCHITECTURE.md sections 5-16).

Each stage is independently runnable and writes only to its own tables, per
IMPLEMENTATION-PLAN.md. Importing this package must not require a database
connection or any API key -- only the stage that persists reaches for a client,
and it does so lazily.
"""
