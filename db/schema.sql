-- UPSC Personal Study Manager: PostgreSQL foundation
-- Safe to run more than once. Existing SQLite tracker.db is NOT modified.
CREATE TABLE IF NOT EXISTS subjects (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_custom BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS topics (
  id BIGSERIAL PRIMARY KEY,
  subject_id BIGINT NOT NULL REFERENCES subjects(id),
  title TEXT NOT NULL,
  topic_key TEXT NOT NULL UNIQUE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_custom BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE(subject_id, title)
);
CREATE TABLE IF NOT EXISTS study_plan_entries (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT NOT NULL REFERENCES topics(id),
  study_date DATE NOT NULL,
  phase TEXT NOT NULL CHECK (phase IN ('study','revision','mixed')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_progress','completed','skipped')),
  mcq_target INTEGER NOT NULL DEFAULT 0 CHECK (mcq_target >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(topic_id, study_date, phase)
);
CREATE INDEX IF NOT EXISTS idx_study_plan_date_status ON study_plan_entries(study_date, status);
CREATE TABLE IF NOT EXISTS study_logs (
  id BIGSERIAL PRIMARY KEY,
  log_date DATE NOT NULL,
  topic_id BIGINT REFERENCES topics(id),
  mcqs_attempted INTEGER NOT NULL DEFAULT 0 CHECK (mcqs_attempted >= 0),
  notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS mcq_attempts (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT REFERENCES topics(id),
  source TEXT NOT NULL DEFAULT 'practice',
  question_ref TEXT,
  selected_answer TEXT,
  correct BOOLEAN,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS revision_schedule (
  topic_id BIGINT PRIMARY KEY REFERENCES topics(id),
  due_date DATE NOT NULL,
  interval_days INTEGER NOT NULL DEFAULT 1 CHECK (interval_days >= 1),
  repetitions INTEGER NOT NULL DEFAULT 0 CHECK (repetitions >= 0),
  ease_factor NUMERIC(4,2) NOT NULL DEFAULT 2.50,
  last_quality SMALLINT CHECK (last_quality BETWEEN 0 AND 5),
  last_reviewed_at DATE
);
CREATE INDEX IF NOT EXISTS idx_revision_due ON revision_schedule(due_date);
CREATE TABLE IF NOT EXISTS mastery_progress (
  topic_id BIGINT PRIMARY KEY REFERENCES topics(id),
  reviews INTEGER NOT NULL DEFAULT 0,
  quality_total NUMERIC(12,2) NOT NULL DEFAULT 0,
  mastery_level SMALLINT NOT NULL DEFAULT 0 CHECK (mastery_level BETWEEN 0 AND 5),
  consecutive_strong INTEGER NOT NULL DEFAULT 0,
  last_quality SMALLINT CHECK (last_quality BETWEEN 0 AND 5),
  last_reviewed_at DATE
);
CREATE TABLE IF NOT EXISTS error_notebook (
  id BIGSERIAL PRIMARY KEY,
  topic_id BIGINT REFERENCES topics(id),
  question_ref TEXT,
  mistake_type TEXT,
  explanation TEXT NOT NULL DEFAULT '',
  resolved BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS tracker_legacy_import (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'sqlite_tracker',
  payload JSONB NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
