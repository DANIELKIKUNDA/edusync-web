-- Lot UX 2026-10 (owner request): optional profile photo of an account.
-- The image itself lives on the private object storage (users/<user_id>/avatar-<sha>.webp), re-encoded server-side
-- (square 256 px WebP, metadata such as EXIF/GPS stripped). This table only keeps the pointer.
-- First scope: platform accounts (Plateforme EduSync). Reachable by the platform role only.
CREATE TABLE IF NOT EXISTS user_avatars (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  object_key varchar(200) NOT NULL CHECK (object_key LIKE 'users/%/avatar-%'),
  content_type varchar(32) NOT NULL CHECK (content_type IN ('image/webp')),
  sha256 char(64) NOT NULL,
  byte_size integer NOT NULL CHECK (byte_size > 0 AND byte_size <= 262144),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version integer NOT NULL DEFAULT 1
);

ALTER TABLE user_avatars ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_avatars FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS avatar_platform ON user_avatars;
    CREATE POLICY avatar_platform ON user_avatars TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT, UPDATE, DELETE ON user_avatars TO edusync_platform;
  END IF;
END $$;
REVOKE ALL ON user_avatars FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN REVOKE ALL ON user_avatars FROM edusync_tenant; END IF;
END $$;
