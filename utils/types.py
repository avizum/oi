"""
GPL-3.0 LICENSE

Copyright (C) 2021-2024  Shobhits7, avizum

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from asyncpg import Record as PGRecord

__all__ = (
    "ErrorDict",
    "LocationDict",
    "ConditionDict",
    "CurrentDict",
    "WeatherDict",
    "UrbanData",
    "BlacklistRecord",
    "PlayerSettingsRecord",
    "SongRecord",
    "PlaylistRecord",
    "PlaylistSongRecord",
    "Blacklist",
    "PlayerSettings",
    "Song",
    "PlaylistSong",
    "Playlist",
)


class ErrorDict(TypedDict):
    code: int
    message: str


class LocationDict(TypedDict):
    name: str
    region: str
    country: str
    lat: float
    lon: float
    tz_id: str
    localtime_epoch: int
    localtime: str


class ConditionDict(TypedDict):
    text: str
    icon: str
    code: int


class CurrentDict(TypedDict):
    last_updated_epoch: int
    last_updated: str
    temp_c: float
    temp_f: float
    is_day: int
    condition: ConditionDict
    wind_mph: float
    wind_kph: float
    wind_degree: int
    wind_dir: str
    pressure_mb: float
    pressure_in: float
    precip_mm: float
    precip_in: float
    humidity: int
    cloud: int
    feelslike_c: float
    feelslike_f: float
    vis_km: float
    vis_miles: float
    uv: float
    gust_mph: float
    gust_kph: float


class WeatherDict(TypedDict):
    error: NotRequired[ErrorDict]
    location: LocationDict
    current: CurrentDict


class UrbanData(TypedDict):
    definition: str
    permalink: str
    thumbs_up: int
    author: str
    word: str
    defid: int
    current_vote: str
    written_on: str
    example: str
    thumbs_down: int


class Record(PGRecord):
    def __getattr__(self, attr: str) -> Any:
        return self[attr]


class BlacklistRecord(Record):
    user_id: int
    reason: str
    moderator: int
    permanent: bool


class PlayerSettingsRecord(Record):
    guild_id: int
    dj_role: int
    dj_enabled: bool
    labels: int


class SongRecord(Record):
    id: int
    identifier: str
    uri: str | None
    encoded: str
    source: str
    title: str
    artist: str


class PlaylistRecord(Record):
    id: int
    author: int
    name: str
    image: str


class PlaylistSongRecord(SongRecord):
    position: str


class Blacklist(TypedDict):
    user_id: int
    reason: str
    moderator: int
    permanent: bool


class PlayerSettings(TypedDict):
    guild_id: int
    dj_role: int
    dj_enabled: bool
    labels: int


class Song(TypedDict):
    id: int
    identifier: str
    uri: str | None
    encoded: str
    source: str
    title: str
    artist: str


class PlaylistSong(Song):
    position: int


class Playlist(TypedDict):
    id: int
    author: int
    name: str
    image: str
    songs: dict[int, PlaylistSong]  # songs are set during runtime
