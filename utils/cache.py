"""
MPL-2.0 LICENSE

The contents of this file are taken from:
https://github.com/Rapptz/RoboDanny/blob/582804d238c8ae302ab9aed6a1b5b8d928ba837f/cogs/utils/cache.py#L34-L68

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

from .types import (
    Blacklist,
    BlacklistRecord,
    PlayerSettings,
    PlayerSettingsRecord,
    Playlist,
    PlaylistRecord,
    PlaylistSongRecord,
    Song,
    SongRecord,
)

if TYPE_CHECKING:
    from core import OiBot


class ExpiringCache(dict):
    def __init__(self, seconds: float):
        self.__ttl: float = seconds
        super().__init__()

    def __verify_cache_integrity(self):
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [k for (k, (v, t)) in self.items() if current_time > (t + self.__ttl)]
        for k in to_remove:
            del self[k]

    def __contains__(self, key: str | int):
        self.__verify_cache_integrity()
        return super().__contains__(key)

    def __getitem__(self, key: str | int):
        self.__verify_cache_integrity()
        return super().__getitem__(key)

    def __setitem__(self, key: str | int, value: Any):
        super().__setitem__(key, (value, time.monotonic()))


class DBCache:
    def __init__(self, bot: OiBot) -> None:
        self.bot: OiBot = bot

        self.blacklisted: dict[int, Blacklist] = {}
        self.player_settings: dict[int, PlayerSettings] = {}
        self.songs: dict[str, Song] = {}
        self.playlists: dict[int, Playlist] = {}

    async def populate(self) -> None:
        pool = self.bot.pool

        blacklisted: list[BlacklistRecord] = await pool.fetch(
            "SELECT user_id, reason, moderator, permanent FROM blacklist", record_class=BlacklistRecord
        )
        player_settings: list[PlayerSettingsRecord] = await pool.fetch(
            "SELECT guild_id, dj_role, dj_enabled  FROM player_settings", record_class=PlayerSettingsRecord
        )
        songs: list[SongRecord] = await pool.fetch(
            "SELECT id, identifier, uri, encoded, source, title, artist FROM songs", record_class=SongRecord
        )
        playlists: list[PlaylistRecord] = await pool.fetch(
            "SELECT id, author, name, image FROM playlists", record_class=PlaylistRecord
        )

        for blacklist in blacklisted:
            self.blacklisted[blacklist.user_id] = dict(blacklist)  # type: ignore

        for setting in player_settings:
            self.player_settings[setting.guild_id] = dict(setting)  # type: ignore

        for song in songs:
            self.songs[song.identifier] = dict(song)  # type: ignore

        for playlist in playlists:
            self.playlists[playlist.id] = dict(playlist)  # type: ignore
            self.playlists[playlist.id]["songs"] = {}

        query = """
                SELECT
                    s.id AS id,
                    s.identifier AS identifier,
                    s.uri AS uri,
                    s.encoded AS encoded,
                    s.source AS source,
                    s.title AS title,
                    s.artist AS artist,
                    ps.position AS position
                FROM
                    playlist_songs ps
                JOIN
                    songs s ON ps.song_id = s.id
                WHERE
                    ps.playlist_id = $1
                ORDER BY
                    ps.position
                """

        for playlist_id in self.playlists.keys():
            playlist_songs: list[PlaylistSongRecord] = await self.bot.pool.fetch(
                query, playlist_id, record_class=PlaylistSongRecord
            )

            for song in playlist_songs:
                self.playlists[playlist_id]["songs"][song.id] = dict(song)  # type: ignore
