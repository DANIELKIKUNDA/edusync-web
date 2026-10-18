-- Annuaire « Utilisateurs & accès » (plateforme), lot 2026-10. Read-only directory: indexes only, no business change.
--
-- Server-side search on the data the directory really holds (name, e-mail), accent and case insensitive, served by a
-- trigram index (edusync_search_key() comes from 0078). Keyset pagination by (lower(full_name), id).
CREATE INDEX IF NOT EXISTS idx_users_search_trgm ON users
  USING gin ((edusync_search_key(full_name || ' ' || email::text)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_users_name_id ON users(lower(full_name), id);
