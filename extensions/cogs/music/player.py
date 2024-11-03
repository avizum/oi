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

import contextlib
from typing import Any, TYPE_CHECKING

import discord
import wavelink
from wavelink import ExtrasNamespace as Extras, Playable, Playlist, QueueMode

from core import OiBot
from utils import format_seconds, PlayerSettingsRecord, SongRecord

from .types import Lyrics, PlayerContext
from .views import PlayerController

if TYPE_CHECKING:
    from wavelink.types.tracks import TrackPayload

    from utils import Song

    from .cog import SEARCH_TYPES

__all__ = ("Player",)


source_map = {
    "YouTube": "ytsearch",
    "YouTube Music": "ytmsearch",
    "Spotify": "spsearch",
    "SoundCloud": "scsearch",
    "Apple Music": "amsearch",
    "Deezer": "dzsearch",
}


class Player(wavelink.Player):
    channel: discord.VoiceChannel | discord.StageChannel
    client: OiBot

    def __call__(self, client: discord.Client, channel: discord.VoiceChannel | discord.StageChannel) -> Player:
        super(wavelink.Player, self).__init__(client, channel)

        return self

    def __init__(self, *args: Any, ctx: PlayerContext, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.ctx: PlayerContext = ctx
        self.loop_track: Playable | None = None
        self.manager: discord.Member | None = None
        self.skip_votes = set()
        self.members: list[discord.Member] = []
        self.controller: PlayerController | None = None
        self.locked: bool = False
        self.bot: OiBot = self.client

        self.dj_enabled: bool = False
        self.dj_role: discord.Role | None = None

    async def _set_player_settings(self) -> None:
        settings = self.client.cache.player_settings.get(self.channel.guild.id)
        if not settings:
            query = """
                INSERT INTO player_settings (guild_id, dj_role, dj_enabled)
                VALUES ($1, $2, $3)
                RETURNING guild_id, dj_role, dj_enabled
            """
            settings = await self.client.pool.fetchrow(
                query, self.channel.guild.id, 0, True, record_class=PlayerSettingsRecord
            )
            self.client.cache.player_settings[self.channel.guild.id] = dict(settings)  # type: ignore

        self.dj_enabled = settings["dj_enabled"]
        self.dj_role = self.channel.guild.get_role(settings["dj_role"])
        if self.dj_enabled and not self.dj_role:
            self.manager = self.ctx.author

    def set_extras(self, playable: Playable, *, requester: str, requester_id: int):
        """Sets the `Playable.extras` attribute.

        Parameters
        ----------
        playable: `Playable`
            The playable to set the extras of.
        requester: `str`
            The name of the requester.
        requester_id: `str`
            The user ID of the requester.
        """
        duration = "LIVE" if playable.is_stream else format_seconds(playable.length / 1000)
        suffix = f" - {playable.author}" if playable.author not in playable.title else ""

        playable.extras = Extras(
            requester=requester,
            requester_id=requester_id,
            duration=duration,
            hyperlink=f"[{playable.title}{suffix}](<{playable.uri}>)",
        )

    async def skip(self) -> Playable | None:
        """Stops the currently playing track.

        Returns
        -------
        Playable | None
            The track that was stopped. None if there was no track playing.
        """
        await super().skip(force=False)

    async def disconnect(self, **kwargs: Any) -> None:
        """Disconnects and disables the player's controller if there is one."""
        if self.controller:
            await self.controller.disable()
        return await super().disconnect(**kwargs)

    def create_now_playing(self, track: Playable | None = None) -> discord.Embed:
        """Creates an embed for the now playing screen."""
        assert self.guild is not None

        nothing = f"Nothing is in the queue. Add some songs with {self.ctx.cog.play.mention}."
        if track is None:
            embed = discord.Embed(
                title="Now Playing",
                description="[Nothing!](https://www.youtube.com/watch?v=dQw4w9WgXcQ)",
                color=0x00FFB3,
            )
            if self.guild.icon:
                embed.set_thumbnail(url=self.guild.icon.url)
            embed.add_field(name="Up Next", value=nothing)
            return embed

        queue_mode = self.queue.mode
        copy_queue = list(self.queue)
        tng = copy_queue[:2] if queue_mode is QueueMode.loop else copy_queue[:3]
        next_tracks = [f"> {tk.extras.hyperlink} | `{tk.extras.duration}` | {tk.extras.requester}" for tk in tng]

        if self.autoplay is not wavelink.AutoPlayMode.disabled:
            nothing = (
                "Autoplay is enabled, but nothing is in the queue. " f"Add some songs with {self.ctx.cog.play.mention}."
            )

        joined = "\n".join(next_tracks) or nothing
        if queue_mode is QueueMode.loop:
            ltrack = self.queue.get()
            joined = (
                f"> [[Looping] {ltrack.title}]({ltrack.uri}) | `{ltrack.extras.duration}` |"
                f" {ltrack.extras.requester}\n{joined}"
            )

        embed = discord.Embed(
            title="Now Playing",
            description=f"{track.extras.hyperlink} | `{track.extras.duration}` | {track.extras.requester}",
            color=0x00FFB3,
        )
        embed.add_field(name="Up Next", value=joined)
        embed.set_thumbnail(url=track.artwork)

        return embed

    async def save_tracks(self, tracks: wavelink.Search) -> dict[str, Song]:
        """Saves a search to the database, and then caches the search."""

        query = """
            INSERT INTO songs (id, identifier, uri, encoded, source, title, artist)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, identifier, uri, encoded, source, title, artist
        """
        songs_data: dict[str, Song] = {}
        for track in tracks:
            if track.identifier not in self.bot.cache.songs:
                # soundcloud's track identifier is too long, so the prefix
                # O:https://api-v2.soundcloud.com/media/ will be removed from all soundcloud tracks.
                if track.source == "soundcloud":
                    track._identifier = track._identifier.removeprefix("O:https://api-v2.soundcloud.com/media/")

                gen_id = self.bot.id_generator.generate()
                song = await self.bot.pool.fetchrow(
                    query,
                    gen_id,
                    track.identifier,
                    track.uri,
                    track.encoded,
                    track.source,
                    track.title,
                    track.author,
                    record_class=SongRecord,
                )
                self.bot.cache.songs[track.identifier] = dict(song)  # type: ignore
                songs_data[track.identifier] = dict(song)  # type: ignore
        return songs_data

    async def decode_track(self, encoded: str) -> Playable | None:
        """Builds a track from a track's encoded information."""
        try:
            data: TrackPayload = await self.node.send("GET", path="v4/decodetrack", params={"encodedTrack": encoded})
            return Playable(data)
        except wavelink.LavalinkException:
            return None

    async def fetch_tracks(self, query: str, source: SEARCH_TYPES, save_tracks: bool = True) -> Playable | Playlist | None:
        """Searches a source for tracks.

        Parameters
        ----------
        query: `str`
            The item to search for.
        source: `SEARCH_TYPES`
            Where to search for tracks.
        save_tracks: `bool`
            Whether to save the tracks to the database. Defualts to `True`

        Returns
        -------
        Playable | Playlist | None
            The results returned by Lavalink.
        """
        try:
            tracks = await Playable.search(query, source=source_map.get(source, "ytsearch"))
            if save_tracks:
                self.bot.loop.create_task(self.save_tracks(tracks if isinstance(tracks, wavelink.Playlist) else tracks[:1]))
        except wavelink.LavalinkLoadException:
            tracks = None

        if not tracks:
            return

        return tracks if isinstance(tracks, wavelink.Playlist) else tracks[0]

    async def invoke_controller(self, playable: Playable | None) -> None:
        """Invokes the controller.

        Parameter
        ---------
        playable: `Playable` | `None`
            The playable to invoke the controller with
        """
        if self.locked:
            return

        embed = self.create_now_playing(playable)
        controller = self.controller

        if not controller:
            controller = PlayerController(ctx=self.ctx, vc=self)
            self.controller = controller

        controller.update_buttons()

        kwargs: dict[str, Any] = dict(embed=embed, view=controller, format_embeds=False, no_tips=True)

        if controller.message is None:
            controller.message = await self.ctx.send(**kwargs)
            return

        elif controller.counter >= 10:
            with contextlib.suppress(discord.NotFound):
                message = await controller.message.fetch()
                await message.edit(view=None)

            controller.message = await self.ctx.send(**kwargs)
            controller.counter = -1
            return

        await controller.update()

    async def fetch_current_lyrics(self) -> Lyrics | None:
        """Searches for the lyrics of the current song."""
        try:
            data: Lyrics = await self.node.send(
                "GET",
                path=f"v4/sessions/{self.node.session_id}/players/{self.ctx.guild.id}/track/lyrics",
            )
            return data
        except (wavelink.LavalinkException, wavelink.NodeException):
            return

    @classmethod
    async def fetch_lyrics(cls, query: str) -> tuple[str, Lyrics] | None:
        """Searches YouTube for lyrics."""
        try:
            tracks = await Playable.search(query, source="ytmsearch")
            if isinstance(tracks, Playlist) or not tracks:
                return
            track = tracks[0]
        except wavelink.LavalinkLoadException:
            return
        try:
            node = wavelink.Pool.get_node("OiBot")
            data: Lyrics = await node.send("GET", path="v4/lyrics", params={"track": f"{track.encoded}"})
            return track.title, data
        except (wavelink.LavalinkException, wavelink.NodeException):
            return
