"""
GPL-3.0 LICENSE

Copyright (C) 2021-present  Shobhits7, avizum

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

import enum
from typing import Any, TYPE_CHECKING, TypedDict

import wavelink

import core

if TYPE_CHECKING:
    from utils import Playlist as PlaylistData

    from .cog import Music
    from .player import Player

__all__ = (
    "PlayerContext",
    "SearchType",
    "TrackEnd",
    "TrackStart",
    "TrackStuck",
)


class SearchType(enum.Enum):
    YouTubeMusic = 1
    Spotify = 2
    SoundCloud = 3
    AppleMusic = 4
    Deezer = 5


class PlayerContext(core.Context):
    cog: Music
    voice_client: Player


class TrackStart(wavelink.TrackStartEventPayload):
    player: Player
    original: wavelink.Playable


class TrackEnd(wavelink.TrackEndEventPayload):
    player: Player


class TrackStuck(wavelink.TrackStuckEventPayload):
    player: Player


class TrackException(wavelink.TrackExceptionEventPayload):
    player: Player


class LyricLine(TypedDict):
    timestamp: int
    duration: int
    line: str
    plugin: Any


class Lyrics(TypedDict):
    sourceName: str
    provider: str
    text: str
    lines: list[LyricLine]
    plugin: Any


class Playlist(wavelink.Playlist):
    def __init__(self, tracks: list[wavelink.Playable], data: PlaylistData) -> None:
        self.tracks = tracks
        self.artwork = data["image"] or self.tracks[0].artwork
        self.name = data["name"]
        self.type = "user_created"
        self.url = None
