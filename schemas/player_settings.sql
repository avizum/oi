CREATE TABLE IF NOT EXISTS player_settings(
    guild_id BIGINT PRIMARY KEY NOT NULL,
    dj_role BIGINT,
    dj_enabled BOOLEAN,
    labels INTEGER NOT NULL DEFAULT 1
)