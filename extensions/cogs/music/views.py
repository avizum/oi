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
import math
from typing import Any, TYPE_CHECKING

import discord
from discord import ButtonStyle, ui
from discord.ext import commands, menus
from wavelink import AutoPlayMode, Playable, QueueMode

from core import ui as cui
from utils import OiView, Paginator

from .utils import hyperlink_song

if TYPE_CHECKING:
    from discord import Emoji, Interaction, PartialEmoji
    from discord.ext.commands import Paginator as CPaginator

    from utils import Playlist, PlaylistSong

    from .player import Player
    from .types import PlayerContext


__all__ = ("PlayerController", "QueuePageSource", "LyricPageSource")


class PlayerButton(ui.Button["PlayerController"]):
    def __init__(
        self,
        *,
        style: ButtonStyle = ButtonStyle.primary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | Emoji | PartialEmoji | None = None,
        row: int | None = None,
    ):
        super().__init__(style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, row=row)

    async def interaction_check(self, itn: discord.Interaction) -> bool:
        assert self.view is not None
        vc: Player = self.view.vc
        if not vc or vc and vc.locked or not vc.connected:
            await itn.response.defer()
            return False
        vc = self.view.vc
        if vc is None or vc.current is None:
            return False
        elif itn.user not in vc.channel.members:
            await itn.response.send_message(f"You need to be in {vc.channel.mention} to use this.", ephemeral=True)
            return False

        if not vc.dj_enabled or itn.user.guild_permissions.manage_guild:
            return True

        if vc.dj_role:
            if vc.dj_role in itn.user.roles:
                return True
            await itn.response.send_message(
                f"You need to have {vc.dj_role.mention} role or have `Manage Server` permission to do this.", ephemeral=True
            )
            return False
        elif not vc.dj_role:
            if vc.manager and vc.manager == itn.user:
                return True
            await itn.response.send_message(
                "You need to be DJ or have `Manage Server` permission to do this.", ephemeral=True
            )
            return False
        else:
            await itn.response.send_message("You need to be a DJ to use this.", ephemeral=True)
            return False


class PlayerSkipButton(PlayerButton):
    async def interaction_check(self, itn: Interaction) -> bool:
        assert self.view is not None
        vc = self.view.vc

        if not vc or vc and vc.locked or not vc.current or not vc.connected:
            await itn.response.defer()
            return False

        if itn.user not in vc.channel.members:
            await itn.response.send_message(f"You need to be in {vc.channel.mention} to use this.", ephemeral=True)
            return False
        return True


class PlayerLyricsButton(PlayerButton):
    async def interaction_check(self, itn: Interaction) -> bool:
        assert self.view is not None
        vc = self.view.vc

        if not vc or vc and vc.locked or not vc.current or not vc.connected:
            await itn.response.defer()
            return False

        return True


class LoopTypeSelect(ui.Select["PlayerController"]):
    def __init__(self, controller: PlayerController):
        self.vc = controller.vc
        self.controller = controller
        vc = self.vc
        assert vc.current is not None
        super().__init__(
            placeholder="Choose loop type...",
            options=[
                discord.SelectOption(
                    emoji="<:loop_one:1294459971014230016>",
                    label=f"Loop {vc.current.title if len(vc.current.title) <= 92 else f'{vc.current.title[:92]}...'}",
                    description="Enable loop for this track only.",
                    value="TRACK",
                ),
                discord.SelectOption(
                    emoji="<:loop_all:1294459877447696385>",
                    label="Loop the Queue",
                    description="Enable loop on the whole queue.",
                    value="QUEUE",
                ),
                discord.SelectOption(
                    emoji="<:stop:1294459644722282577>",
                    label="Disable Loop",
                    description="Disable looping.",
                    value="DISABLE",
                ),
            ],
        )

    async def callback(self, itn: Interaction) -> Any:
        assert self.view is not None
        if not self.values:
            await itn.response.defer()
        else:
            ctx: PlayerContext = self.vc.ctx
            disable = self.values[0] == "DISABLE"
            loop_queue = self.values[0] == "QUEUE"
            self.controller.loop.emoji = (
                "<:loop_all:1294459877447696385>" if loop_queue else "<:loop_one:1294459971014230016>"
            )
            self.controller.loop.style = discord.ButtonStyle.green
            if disable:
                self.vc.queue.mode = QueueMode.normal
                ctx.bot.command_usage["player loop"] += 1
            elif loop_queue:
                self.vc.queue.mode = QueueMode.loop_all
                ctx.bot.command_usage["queue loop"] += 1
            else:
                self.vc.queue.mode = QueueMode.loop
                ctx.bot.command_usage["player loop"] += 1
            self.controller.remove_item(self)
            self.controller.loop_select = None
            await self.controller.update(itn)


class PlayerController(ui.View):
    def __init__(self, /, *, ctx: PlayerContext, vc: Player) -> None:
        self.ctx: PlayerContext = ctx
        self.vc: Player = vc
        self.message: discord.Message | None = None
        self.counter: int = -1
        self.is_updating: bool = False
        self.loop_select: LoopTypeSelect | None = None
        self.lyrics_paginators: dict[int, Paginator] = {}
        super().__init__(timeout=None)
        self.update_buttons()

    @property
    def labels(self) -> int:
        return self.vc.labels

    @labels.setter
    def labels(self, state: int) -> None:
        self.vc.labels = state

    async def disable(self) -> None:
        self.stop()
        self.vc.controller = None
        if self.message is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await self.message.edit(view=None)

    def set_disabled(self, disabled: bool) -> None:
        for item in self.children:
            if isinstance(item, PlayerButton):
                item.disabled = disabled

    def set_labels(self) -> None:
        vc = self.vc
        if self.labels == 2:
            self.rewind.label = "Rewind"
            self.pause.label = "Resume" if vc.paused else "Pause"
            self.skip.label = "Skip"
            self.shuffle.label = "Shuffle"
            if vc.queue.mode is QueueMode.normal:
                self.loop.label = "Loop"
            elif vc.queue.mode is QueueMode.loop:
                self.loop.label = "Looping One"
            elif vc.queue.mode is QueueMode.loop_all:
                self.loop.label = "Looping Queue"
            self.autoplay.label = "Autoplay"
            self.lyrics.label = "Lyrics"
        elif self.labels == 1:
            for item in self.children:
                if isinstance(item, PlayerButton) and item.label is not None:
                    item.label = None

    def set_visible(self, visible: bool = True) -> None:
        self.clear_items()
        if visible:
            self.add_item(self.rewind)
            self.add_item(self.pause)
            self.add_item(self.skip)
            self.add_item(self.shuffle)
            self.add_item(self.loop)
            self.add_item(self.autoplay)
            self.add_item(self.lyrics)
            if self.loop_select:
                self.add_item(self.loop_select)

    def update_buttons(self) -> None:
        if self.labels == 0:
            self.set_visible(False)
            return

        self.set_visible()
        self.set_labels()
        self.set_disabled(False)

        self.pause.style = ButtonStyle.gray
        self.loop.style = ButtonStyle.gray
        self.autoplay.style = ButtonStyle.gray
        self.loop.emoji = "<:loop_all:1294459877447696385>"

        vc = self.vc

        if vc.queue.mode is not QueueMode.normal:
            self.loop.style = ButtonStyle.green
            if vc.queue.mode == QueueMode.loop:
                self.loop.emoji = "<:loop_one:1294459971014230016>"

        if vc.autoplay is not AutoPlayMode.disabled:
            self.autoplay.style = ButtonStyle.green

        if vc.paused:
            self.pause.style = ButtonStyle.red

        if len(vc.queue) <= 1:
            self.shuffle.disabled = True

        if vc.current is None:
            self.set_disabled(True)

    async def update(self, itn: Interaction | None = None, /, *, invoke: bool = True) -> None:
        if self.is_updating or self.is_finished() or self.message is None:
            return

        self.is_updating = True

        if itn and itn.is_expired() or itn and itn.response.is_done():
            itn = None

        if not itn and type(self.message) is not discord.Message:
            try:
                self.message = await self.message.fetch()
            except discord.NotFound:
                self.message = None
                return

        edit = itn.response.edit_message if itn and not itn.response.is_done() else self.message.edit
        current = self.vc.current

        if self.counter >= 10:
            await edit(view=None)
            if invoke:
                self.message = None
                self.counter = -1
                await self.vc.invoke_controller(current)
                self.is_updating = False
                return
            self.is_updating = False
            return

        self.update_buttons()
        await edit(embed=self.vc.create_now_playing(current), view=self)

        self.is_updating = False

    def is_manager(self, itn: Interaction) -> bool:

        vc = self.vc

        assert vc.current is not None
        assert isinstance(itn.user, discord.Member)

        if not vc.dj_enabled or itn.user.guild_permissions.manage_guild:
            return True

        if vc.dj_role:
            if vc.dj_role in itn.user.roles:
                return True
            return False
        elif not vc.dj_role:
            if vc.manager == itn.user:
                return True
            return False
        return True

    @cui.button(cls=PlayerButton, emoji="<:skip_left:1294459900696461364>")
    async def rewind(self, itn: Interaction, _: PlayerButton):
        await self.vc.seek(0)
        if self.vc.paused:
            await self.vc.pause(False)
        self.ctx.bot.command_usage["seek"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerButton, emoji="<:play_or_pause:1294459947572138069>")
    async def pause(self, itn: Interaction, _: PlayerButton):
        await self.vc.pause(not self.vc.paused)
        self.ctx.bot.command_usage["pause" if not self.vc.paused else "resume"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerSkipButton, emoji="<:skip_right:1294459785130934293>")
    async def skip(self, itn: Interaction, _: PlayerSkipButton):
        vc = self.vc

        assert self.vc.current is not None
        assert isinstance(itn.user, discord.Member)

        send = itn.followup.send if itn.response.is_done() else itn.response.send_message

        if self.is_manager(itn):
            await self.vc.skip()
            await send(f"{itn.user} has skipped the track.")
        elif self.vc.current.extras.requester_id == itn.user.id:
            await self.vc.skip()
            await send(f"Track requester {itn.user} has skipped the track.")
        else:
            required = math.ceil(len(vc.channel.members) / 2)
            if itn.user.id in self.vc.skip_votes:
                await send("You already voted to skip the track.", ephemeral=True)
                return
            self.vc.skip_votes.add(itn.user.id)
            if len(self.vc.skip_votes) >= required:
                await self.vc.skip()
                await send(f"Vote to skip passed ({required} of {required}). Skipping.")
                return
            await send(f"Voted to skip. ({len(self.vc.skip_votes)}/{required})", ephemeral=True)
        self.ctx.bot.command_usage["skip"] += 1
        await self.update(itn, invoke=False)

    @cui.button(cls=PlayerButton, emoji="<:shuffle:1294459691119935600>")
    async def shuffle(self, itn: Interaction, _: PlayerButton):
        vc = self.vc

        vc.queue.shuffle()
        self.ctx.bot.command_usage["queue shuffle"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerButton, emoji="<:loop_all:1294459877447696385>")
    async def loop(self, itn: Interaction, button: PlayerButton):
        assert self.vc.current is not None

        if not self.loop_select:
            self.loop_select = LoopTypeSelect(self)
            self.add_item(self.loop_select)
        else:
            self.remove_item(self.loop_select)
            self.loop_select = None
        await self.update(itn)

    @cui.button(cls=PlayerButton, emoji="<:autoplay:1294460017348710420>")
    async def autoplay(self, itn: Interaction, button: PlayerButton):
        state = AutoPlayMode.disabled if self.vc.autoplay == AutoPlayMode.enabled else AutoPlayMode.enabled
        self.vc.autoplay = state
        self.ctx.bot.command_usage["player autoplay"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerLyricsButton, emoji="<:lyrics:1297669978635505675>")
    async def lyrics(self, itn: Interaction, button: PlayerLyricsButton):
        assert self.vc.current is not None

        self.ctx.bot.command_usage["lyrics"] += 1

        if itn.user.id in self.lyrics_paginators:
            paginator = self.lyrics_paginators[itn.user.id]
            assert isinstance(paginator.source, LyricPageSource)

            if paginator.message:
                with contextlib.suppress(discord.NotFound):
                    await paginator.message.delete()
            paginator.stop()
            del self.lyrics_paginators[itn.user.id]

        await itn.response.defer(thinking=True, ephemeral=True)
        lyrics_data = await self.vc.fetch_current_lyrics()
        if not lyrics_data or lyrics_data and not lyrics_data["text"]:
            await itn.followup.send("Could not find lyrics.", ephemeral=True)
            return
        pag = commands.Paginator(max_size=320)

        for line in lyrics_data["text"].splitlines():
            pag.add_line(line)

        source = LyricPageSource(self.vc.current.title, pag)
        paginator = LyricsPaginator(
            source, ctx=self.ctx, delete_message_after=True, timeout=((self.vc.current.length / 1000) * 2)
        )  # Double the track's length

        await paginator.start(itn)
        self.lyrics_paginators[itn.user.id] = paginator


class QueuePageSource(menus.ListPageSource):
    def __init__(self, player: Player) -> None:
        self.vc = player
        super().__init__(entries=list(enumerate(list(player.queue), start=1)), per_page=8)

    async def format_page(self, _: menus.Menu, tracks: list[tuple[int, Playable]]):
        ctx = self.vc.ctx
        embed = discord.Embed(title=f"Up Next in {ctx.guild.name}", color=0x00FFB3)
        up_next = ""
        for count, track in tracks:
            if len(track._title) > 90:
                track._title = f"{track._title[:50]}..."
                track.extras.hyperlink = f"[{track.title}]({track.uri})"
            up_next = f"{up_next}\n{count}. {track.extras.hyperlink} | {track.extras.requester}"
        embed.description = up_next
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        return embed


class PlaylistPageSource(menus.ListPageSource):
    def __init__(self, playlist: Playlist) -> None:
        self.playlist: Playlist = playlist
        self.songs: dict[int, PlaylistSong] = self.playlist["songs"]
        super().__init__(list(self.songs.keys()), per_page=8)

    async def format_page(self, _: menus.Menu, playlist_ids: list[int]) -> discord.Embed:
        lines = []

        for p_id in playlist_ids:
            song = self.songs[p_id]
            if len(song["title"]) > 90:
                song["title"] = f"{song["title"][: len(song["artist"])]}..."
            lines.append(f"{song["position"]}. {hyperlink_song(song)} - {song["artist"]}")

        embed = discord.Embed(title=f"Playlist Info: {self.playlist["name"]}", description="\n".join(lines))
        embed.set_thumbnail(url=self.playlist.get("image"))
        embed.set_footer(text=f"{len(self.songs)} songs in {self.playlist["name"]}")
        return embed


class LyricPageSource(menus.ListPageSource):
    def __init__(self, title: str, paginator: CPaginator):
        self.title = title
        super().__init__(paginator.pages, per_page=1)

    async def format_page(self, menu: menus.MenuPages, page: str) -> discord.Embed:
        return discord.Embed(title=f"{self.title} lyrics", description=page, color=0x00FFB3)


class LyricsPaginator(Paginator):
    async def interaction_check(self, _: Interaction):
        # All instances of this paginator are sent ephemerally
        return True

    async def start(self, itn: Interaction):
        await self.source._prepare_once()
        page = await self.source.get_page(self.current_page)
        kwargs = await self._get_kwargs(page)
        await self._update(self.current_page)

        if itn.response.is_done():
            msg = await itn.followup.send(**kwargs, view=self, wait=True, ephemeral=True)
        else:
            await itn.response.send_message(**kwargs, view=self, ephemeral=True)
            msg = await itn.original_response()

        self.message = msg


class PlaylistInfoModal(ui.Modal):
    playlist = discord.ui.TextInput(
        label="Enter a name",
        style=discord.TextStyle.short,
        placeholder="My Playlist",
        required=True,
        min_length=1,
        max_length=100,
    )
    image = discord.ui.TextInput(
        label="Enter an image URL",
        style=discord.TextStyle.short,
        required=False,
    )

    def __init__(self, title: str, *, name: str | None = None, image: str | None = None) -> None:
        self.name: str
        self.url: str | None = None

        self.playlist.default = name
        self.image.default = image
        super().__init__(title=title)

    async def on_submit(self, itn: Interaction) -> None:
        await itn.response.defer()
        self.name = self.playlist.value
        self.url = self.image.value


class PlaylistModalView(OiView):
    def __init__(
        self, *, title: str, playlist: Playlist | None = None, members: list[discord.Member | discord.User], timeout=180
    ):
        self.title: str = title
        self.playlist: Playlist | None = playlist
        self.name: str = ""
        self.url: str | None = None
        if playlist:
            self.name = playlist["name"]
            self.url = playlist["image"]

        super().__init__(members=members, timeout=timeout)
        self.open_modal.label = title

    async def on_timeout(self):
        if self.message and not self.name:
            self.open_modal.disabled = True
            await self.message.edit(content="Timed out.", view=self)

    @ui.button(style=discord.ButtonStyle.green)
    async def open_modal(self, itn: Interaction, button: ui.Button) -> None:
        name = self.playlist["name"] if self.playlist else None
        image = self.playlist.get("image") if self.playlist else None
        modal = PlaylistInfoModal(self.title, name=name, image=image)
        await itn.response.send_modal(modal)
        await modal.wait()
        self.name = modal.name
        self.url = modal.url
        self.stop()
