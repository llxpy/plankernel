-- 盘枢 KBEngine 初始 schema（基线 SQLite >= 3.37.2）
-- docs / chunks / FTS5 / retrieval_score / integrity / pivot / budget / config

CREATE TABLE IF NOT EXISTS docs (
  doc_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id   TEXT NOT NULL,
  rel_path       TEXT NOT NULL,
  abs_path       TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  size_bytes     INTEGER NOT NULL DEFAULT 0,
  mime           TEXT NOT NULL DEFAULT '',
  page_count     INTEGER,
  doc_meta       TEXT NOT NULL DEFAULT '{}',
  parser_version TEXT NOT NULL DEFAULT '',
  status         TEXT NOT NULL DEFAULT 'pending',
  error_msg      TEXT,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL,
  indexed_at     INTEGER,
  UNIQUE (workspace_id, rel_path, content_sha256)
);
CREATE INDEX IF NOT EXISTS idx_docs_sha ON docs(content_sha256);
CREATE INDEX IF NOT EXISTS idx_docs_status ON docs(status, updated_at);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  workspace_id   TEXT NOT NULL,
  doc_id         INTEGER NOT NULL REFERENCES docs(doc_id) ON DELETE CASCADE,
  seq            INTEGER NOT NULL,
  parent_id      INTEGER,
  title          TEXT NOT NULL DEFAULT '',
  content        TEXT NOT NULL,
  content_seg    TEXT NOT NULL,
  token_count    INTEGER NOT NULL DEFAULT 0,
  byte_offset    INTEGER NOT NULL DEFAULT 0,
  page_start     INTEGER,
  page_end       INTEGER,
  merge_strategy TEXT NOT NULL DEFAULT 'rule',
  hash           TEXT NOT NULL,
  created_at     INTEGER NOT NULL,
  UNIQUE (workspace_id, doc_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, seq);
CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(hash);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  title,
  content,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, chunk_id, title, content)
  VALUES (new.rowid, new.chunk_id, new.title, new.content_seg);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, title, content)
  VALUES ('delete', old.rowid, old.chunk_id, old.title, old.content_seg);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, title, content)
  VALUES ('delete', old.rowid, old.chunk_id, old.title, old.content_seg);
  INSERT INTO chunks_fts(rowid, chunk_id, title, content)
  VALUES (new.rowid, new.chunk_id, new.title, new.content_seg);
END;

CREATE TABLE IF NOT EXISTS retrieval_score (
  query_run_id TEXT NOT NULL,
  chunk_id     INTEGER NOT NULL,
  route        TEXT NOT NULL,
  rank         INTEGER NOT NULL,
  raw_score    REAL NOT NULL,
  norm_score   REAL NOT NULL DEFAULT 0,
  fused        REAL GENERATED ALWAYS AS (
      CASE route WHEN 'fused' THEN norm_score ELSE 0 END
  ) STORED,
  created_at   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (query_run_id, route, chunk_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_score_fused ON retrieval_score(query_run_id, fused DESC);
CREATE INDEX IF NOT EXISTS idx_score_route ON retrieval_score(query_run_id, route, norm_score DESC);

CREATE TABLE IF NOT EXISTS integrity_chain (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  scope        TEXT NOT NULL,
  scope_key    TEXT NOT NULL DEFAULT '',
  prev_hash    TEXT NOT NULL DEFAULT '',
  payload_hash TEXT NOT NULL,
  state_b64    TEXT NOT NULL,
  nonce_b64    TEXT NOT NULL,
  level        INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chain_scope_seq ON integrity_chain(scope, seq);

CREATE TABLE IF NOT EXISTS pivot_cache (
  query_hash   TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  query_text   TEXT NOT NULL,
  pivots_json  TEXT NOT NULL,
  model        TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd      REAL NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL,
  hit_count     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pivot_ws ON pivot_cache(workspace_id, created_at);

CREATE TABLE IF NOT EXISTS llm_budget (
  bucket       TEXT PRIMARY KEY,
  period_key   TEXT NOT NULL,
  requests     INTEGER NOT NULL DEFAULT 0,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd      REAL NOT NULL DEFAULT 0,
  limit_usd     REAL NOT NULL,
  updated_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS config_kv (
  namespace  TEXT NOT NULL,
  key        TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (namespace, key)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_state (
  workspace_id TEXT PRIMARY KEY,
  state        TEXT NOT NULL,
  reason       TEXT NOT NULL DEFAULT '',
  updated_at   INTEGER NOT NULL
);
