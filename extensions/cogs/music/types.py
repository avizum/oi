from __future__ import annotations

import enum
from typing import Any, TYPE_CHECKING

import discord
import wavelink

import core

if TYPE_CHECKING:
    from .player import Player

__all__ = (
    "SearchType",
    "PlayerContext",
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
