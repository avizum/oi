CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    user_id BIGINT NOT NULL
)

CREATE TABLE playlist_songs (
    playlist_id TEXT NOT NULL,
    encoded TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    position INT NOT NULL
)