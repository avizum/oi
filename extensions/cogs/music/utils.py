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

import datetime
from typing import Annotated, Any, ClassVar, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import _human_join as human_join
from rapidfuzz import process

from utils import Playlist as PlaylistD, Song as SongD

if TYPE_CHECKING:
    from core import OiBot

    from .types import PlayerContext


__all__ = (
    "Playlist",
    "Song",
    "Time",
    "find_song_matches",
    "hyperlink_song",
    "is_in_channel",
    "is_in_voice",
    "is_manager",
    "is_not_deafened",
)

type Interaction = discord.Interaction[OiBot]


class TimeConverter(app_commands.Transformer):
    """Converts a time `MM:SS` to an `int`"""

    def base(self, ctx: PlayerContext, argument: int | str) -> int:
        try:
            argument = int(argument)
        except ValueError:
            pass
        if isinstance(argument, int):
            return argument

        try:
            time_ = datetime.datetime.strptime(argument, "%M:%S")
            delta = time_ - datetime.datetime(1900, 1, 1)
        except ValueError as e:
            raise commands.BadArgument("Time must be in MM:SS format.") from e
        else:
            return int(delta.total_seconds())

    async def convert(self, ctx: PlayerContext, argument: int | str) -> int:
        return self.base(ctx, argument)

    async def transform(self, itn: Interaction, argument: int | str) -> int:
        ctx: PlayerContext = itn._baton
        return self.base(ctx, argument)


class PlaylistConverter(app_commands.Transformer):
    """Converts to a `Playlist`."""

    def base(self, ctx: PlayerContext, playlist_id: str) -> PlaylistD:
        try:
            query = int(playlist_id)
        except ValueError:
            query = playlist_id

        if isinstance(query, int):
            playlist = ctx.bot.cache.playlists.get(query)
            if playlist and playlist["author"] == ctx.author.id:
                return playlist
            raise commands.BadArgument(f"Could not find playlist with ID {playlist_id}.")

        for playlist in ctx.bot.cache.playlists.values():
            if playlist["name"].lower() == query.lower() and playlist["author"] == ctx.author.id:
                return playlist
        raise commands.BadArgument(f"Could not find playlist named {playlist_id}.")

    async def convert(self, ctx: PlayerContext, argument: str) -> PlaylistD:
        return self.base(ctx, argument)

    async def transform(self, itn: Interaction, value: str) -> PlaylistD:
        ctx: PlayerContext = itn._baton
        return self.base(ctx, value)


class SongConverter(app_commands.Transformer):
    """Converts to a `Song`"""

    async def base(self, ctx: PlayerContext, song_id: str) -> SongD | str:
        song = ctx.bot.cache.songs.get(song_id)
        if song:
            return song

        for data in ctx.bot.cache.songs.values():
            if data["title"].lower() == song_id.lower():
                return data
        return song_id

    async def convert(self, ctx: PlayerContext, argument: str) -> SongD | str:
        return await self.base(ctx, argument)

    async def transform(self, itn: Interaction, value: str) -> SongD | str:
        ctx: PlayerContext = itn._baton
        return await self.base(ctx, value)


class LabelsConverter(app_commands.Transformer):
    _choices: ClassVar[list[tuple[str, int]]] = [
        ("Nothing", 0),
        ("Emojis", 1),
        ("Emojis and labels", 2),
    ]

    @property
    def type(self):
        return discord.AppCommandOptionType.integer

    @property
    def choices(self) -> list[app_commands.Choice]:
        return [app_commands.Choice(name=name, value=value) for name, value in self._choices]

    @classmethod
    async def convert(cls, _: PlayerContext, argument: str) -> int:
        names = []
        for name, value in cls._choices:
            if argument.lower() == name.lower():
                return value
            names.append(f'"{name}"')

        raise commands.BadArgument(f'Could not convert "{argument}" into the choices {human_join(names)}')

    @classmethod
    async def transform(cls, _: Interaction, argument: int) -> int:
        return argument


Playlist = Annotated[PlaylistD, PlaylistConverter]
Song = Annotated[SongD | str, SongConverter]
Time = Annotated[int, TimeConverter]
Labels = Annotated[int, LabelsConverter]


SOURCES: dict[str, str] = {
    "youtube": "YouTube",
    "spotify": "Spotify",
    "soundcloud": "Sound Cloud",
    "applemusic": "Apple Music",
    "deezer": "Deezer",
}


def format_option_name(song: SongD) -> str:
    """Formats a `Song` like so: `SONG NAME - ARTIST (SOURCE)`.

    If the total length is longer than 100 characters, the song name will be truncated.
    """
    suffix = f" - {song["artist"]} ({SOURCES[song["source"]]})"
    max_title_length = 100 - len(suffix)

    title = song["title"]

    if len(title) > max_title_length:
        title = f"{title[:max_title_length - 3]}..."
    return f"{title}{suffix}"


def find_song_matches(items: dict[str, Any], current: str) -> list[app_commands.Choice[str]]:
    """Matches a string to the items provided.

    Parameters
    ----------
    items: `dict[str, Any]`
        The items to match.
    current: `str`
        The string to match against the items.

    Returns
    -------
    list[app_commands.Choice[str]]
        A list of choices that matched the items.
    """
    matches = process.extract(current.lower(), items.keys(), limit=25, score_cutoff=65.0)

    options: list[app_commands.Choice[str]] = []
    for match in matches:
        title, _, _ = match
        options.extend(
            [app_commands.Choice(name=format_option_name(song), value=song["identifier"]) for song in items[title]]
        )
    return options[:25]


def hyperlink_song(song: SongD) -> str:
    """Creates a hyperlink from `Song`."""
    if song["uri"]:
        return f"[{song["title"]}](<{song["uri"]}>)"
    return song["title"]


def is_in_voice(*, author: bool = True, bot: bool = True):
    """Checks if a member or bot is in the voice channel."""

    def inner(ctx: PlayerContext) -> bool:
        if author and bot:
            if ctx.author.voice and ctx.voice_client and ctx.author.voice.channel == ctx.voice_client.channel:
                return True
            if ctx.voice_client and not ctx.author.voice:
                raise commands.CheckFailure(
                    f"You need to be connected to {ctx.voice_client.channel.mention} to use this command."
                )

            raise commands.CheckFailure("There is no music player connected.")
        if author:
            if ctx.author.voice:
                return True
            raise commands.CheckFailure("You need to be connected to a voice channel to use this command.")
        if bot:
            if ctx.voice_client:
                return True
            raise commands.CheckFailure("There is no music player connected.")
        raise commands.CheckFailure("Uh oh.")

    return commands.check(inner)


def is_in_channel():
    """Checks if the current channel is the bound channel."""

    def inner(ctx: PlayerContext) -> bool:
        vc = ctx.voice_client
        if vc and ctx.channel != vc.ctx.channel:
            raise commands.CheckFailure(f"This command can only be ran in {vc.ctx.channel.mention}, not here.")
        return True

    return commands.check(inner)


def is_not_deafened():
    """Checks if a member is deafened."""

    def inner(ctx: PlayerContext) -> bool:
        voice = ctx.author.voice
        if voice and voice.self_deaf:
            raise commands.CheckFailure("You can not use this command while deafened.")
        return True

    return commands.check(inner)


def is_manager():
    """Checks if a member is a player "manager".

    Manager is determined as follows:
    - If DJ is disabled, anyone is a manager.
    - If DJ is enabled and:
        - DJ role is enabled, anyone with DJ role is a manager.
        - DJ role is disabled, the first user of a session is a manager.
    Note: Anybody with Manage Guild permissions is alawys a manager.
    """

    def inner(ctx: PlayerContext) -> bool:
        vc = ctx.voice_client

        if not vc.dj_enabled or ctx.author.guild_permissions.manage_guild:
            return True

        if vc.dj_role:
            if vc.dj_role in ctx.author.roles:
                return True
            raise commands.CheckFailure(
                f"You need to have {vc.dj_role.mention} role or have `Manage Server` permissions to do this."
            )
        if not vc.dj_role:
            if vc.manager == ctx.author:
                return True
            raise commands.CheckFailure("You need to be DJ or have `Manage Server` permission to do this.")

        return True

    return commands.check(inner)
