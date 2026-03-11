-- FireReach — Supabase SQL Setup
-- Run these once in the Supabase SQL Editor to create required tables.
-- Enable pgvector extension for the optional vector memory feature.

-- ── Jobs table (top-level job tracking) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id           BIGSERIAL PRIMARY KEY,
    job_id       UUID        NOT NULL UNIQUE,
    company_name TEXT        NOT NULL,
    company_domain TEXT      NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'queued',
    icp_score    INT,
    icp_label    TEXT,
    error_message TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Agent Events (SSE source) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_events (
    id        BIGSERIAL PRIMARY KEY,
    job_id    UUID        NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    stage     TEXT,
    message   TEXT,
    status    TEXT        NOT NULL DEFAULT 'running',
    data      JSONB       NOT NULL DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_events_job_id ON agent_events(job_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_timestamp ON agent_events(timestamp);

-- ── Outreach Log (audit + idempotency) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_log (
    id             BIGSERIAL PRIMARY KEY,
    message_id     TEXT,
    recipient      TEXT        NOT NULL,
    company        TEXT        NOT NULL,
    dedup_key      TEXT        NOT NULL UNIQUE,
    subject        TEXT,
    body_preview   TEXT,
    quality_score  FLOAT,
    signals_cited  TEXT[]      DEFAULT '{}',
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status         TEXT        NOT NULL DEFAULT 'sent'
);

CREATE INDEX IF NOT EXISTS idx_outreach_dedup ON outreach_log(dedup_key);

-- ── Suppression List (bounces & unsubscribes) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS suppression (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT        NOT NULL UNIQUE,
    reason     TEXT        NOT NULL DEFAULT 'unsubscribe',
    added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Optional: Vector Memory (pgvector) ───────────────────────────────────────
-- Uncomment to enable the persistent learning loop (Section 7.3 of the blueprint).
--
-- CREATE EXTENSION IF NOT EXISTS vector;
--
-- CREATE TABLE IF NOT EXISTS outreach_memory (
--     id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--     company_domain TEXT        NOT NULL,
--     brief_text     TEXT,
--     embedding      vector(768),
--     created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- CREATE INDEX IF NOT EXISTS idx_memory_embedding
--   ON outreach_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
