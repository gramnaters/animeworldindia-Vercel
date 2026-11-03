CREATE TABLE IF NOT EXISTS mappings (
  imdb_id TEXT PRIMARY KEY,
  tmdb_id TEXT,
  slug TEXT NOT NULL,
  content_type TEXT,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS failed_mappings (
  imdb_id TEXT PRIMARY KEY,
  created_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_mappings_slug ON mappings(slug);

CREATE TABLE IF NOT EXISTS slug_imdb (
  slug TEXT PRIMARY KEY,
  tmdb_id TEXT,
  imdb_id TEXT,
  content_type TEXT,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS as_map (imdb_id TEXT PRIMARY KEY, slug TEXT, type TEXT, title TEXT, created_at INTEGER);
