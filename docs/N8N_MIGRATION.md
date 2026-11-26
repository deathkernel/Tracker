# n8n migration foundation

This branch adds a PostgreSQL schema and two importable n8n workflow templates. It deliberately does not change or delete the current FastAPI/SQLite application.

## Recommended database

Use PostgreSQL for the new n8n-backed system. It is a better fit than SQLite for concurrent n8n executions, transactions, indexes, JSONB legacy snapshots and future phone/dashboard access. Keep the current SQLite `tracker.db` as the source of truth until migration verification is complete.

## Phase 0 — safety first

1. Stop the Tracker app and make a separate copy of `tracker.db` (also export the in-app JSON backup).
2. Keep the original repo on `main`; use this feature branch for migration work.
3. Start PostgreSQL as a separate Docker service with a persistent named volume. Do not put the database password in workflow JSON or commit it.
4. Run `db/schema.sql` against the new PostgreSQL database.
5. Import the complete Tracker JSON export into `tracker_legacy_import.payload` before transforming anything. This preserves every existing field, including fields not yet mapped to normalized tables.

## Current data shape

The current backend stores one versioned JSON state in SQLite table `app_state`, row `id=1`. It includes topics, daily/weekly state, logs, study-plan completion/progress, revision schedule, test results, error notebook, question bank, mastery, retests, recovery queue, exam session, custom subjects and settings. Do not assume the JSON keys are identical to the normalized SQL column names; map them explicitly and verify counts.

## Study rules to preserve

- A topic's Day 1 is preparation.
- Day 2 is revision + exactly 50 MCQs; no new topic is assigned to that same topic's Day 2.
- Different topics may overlap (one topic Day 1 while another is Day 2), matching the current Tracker's documented behaviour.
- Shuffle subjects while respecting the saved roadmap and completed work.
- 4 focused study hours/day target and 50 MCQs/day target.
- Sunday is mixed revision.
- Preserve PYQ bank, test snapshots/attempts, error notebook, mastery and retest history.

## Workflow templates

Import JSON files from `n8n/workflows/` in n8n (Workflows → Import from File). They are intentionally read-only starter workflows; they do not create or mutate study records. Configure a Postgres credential named in n8n, then select it on each Postgres node.

- `daily-study-queue.json`: 06:00 Asia/Kolkata schedule; returns today's planned topics.
- `due-revision-queue.json`: 07:00 Asia/Kolkata schedule; returns due revision topics.

The templates expect normalized tables from `db/schema.sql`. Until the data migration is complete, they will return empty results (or fail if the schema has not been applied).

## Migration acceptance checks

Before switching the dashboard or retiring SQLite, compare:
- subject count and topic count;
- study-plan entry count and per-date phase counts;
- completed topic count;
- MCQ/test attempt count and question-bank count;
- error notebook count;
- revision/mastery/retest records;
- settings and exam target date;
- a full export from PostgreSQL against the preserved legacy JSON snapshot.

Only switch reads/writes after all checks pass and a rollback path is tested. Keep SQLite untouched for at least one complete study cycle after cutover.
