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
from wavelink import Playable, Playlist, QueueMode

from core import OiBot

from .types import Lyrics, PlayerContext
from .views import PlayerController

if TYPE_CHECKING:
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
        self.privileged: discord.Member | None = ctx.author
        self.skip_votes = set()
        self.members: list[discord.Member] = []
        self.controller: PlayerController | None = None
        self.locked: bool = False

    async def skip(self) -> Playable | None:
        await super().skip(force=False)

    async def disconnect(self, **kwargs: Any) -> None:
        if self.controller:
            await self.controller.disable()
        return await super().disconnect(**kwargs)

    def create_now_playing(self, track: Playable | None = None) -> discord.Embed:
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

    async def fetch_tracks(self, query: str, source: SEARCH_TYPES) -> Playable | Playlist | None:
        try:
            tracks = await Playable.search(query, source=source_map.get(source, "ytsearch"))
        except wavelink.LavalinkLoadException:
            tracks = None

        if not tracks:
            return

        return tracks if isinstance(tracks, wavelink.Playlist) else tracks[0]

    async def invoke_controller(self, playable: Playable) -> None:
        if self.locked:
            return

        embed = self.create_now_playing(playable)
        controller = self.controller

        if not controller:
            controller = PlayerController(ctx=self.ctx, vc=self)
            self.controller = controller

        controller.update_buttons()

        if controller.message is None:
            controller.message = await self.ctx.send(embed=embed, view=controller, format_embeds=False)
            return

        elif controller.counter >= 10:
            with contextlib.suppress(discord.NotFound):
                message = await controller.message.fetch()
                await message.edit(view=None)

            controller.message = await self.ctx.send(embed=embed, view=controller, format_embeds=False)
            controller.counter = -1
            return

        await controller.update()

    async def fetch_current_lyrics(self) -> Lyrics | None:
        try:
            data: Lyrics = await self.node.send(
                "GET",
                path=f"v4/sessions/{self.node.session_id}/players/{self.ctx.guild.id}/track/lyrics?skipTrackSource=true",
            )
            return data
        except (wavelink.LavalinkException, wavelink.NodeException):
            return

    @classmethod
    async def fetch_lyrics(cls, query: str) -> tuple[str, Lyrics] | None:
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
