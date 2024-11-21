CREATE TABLE IF NOT EXISTS command_usage(
    id SERIAL PRIMARY KEY,
    command_name TEXT,
    guild_id BIGINT,
    channel_id BIGINT,
    user_id BIGINT,
    used TIMESTAMP WITH TIMEZONE,
    app_command BOOLEAN,
    success BOOLEAN
)