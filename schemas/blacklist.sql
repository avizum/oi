CREATE TABLE IF NOT EXISTS blacklist (
    user_id BIGINT PRIMARY KEY NOT NULL,
    reason TEXT NOT NULL,
    moderator BIGINT NOT NULL,
    permanent BOOLEAN NOT NULL
)