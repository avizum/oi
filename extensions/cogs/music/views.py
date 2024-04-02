from __future__ import annotations

import asyncio
import contextlib
import math
from typing import Any, TYPE_CHECKING

import discord
from discord import ButtonStyle, ui
from discord.ext import menus
from wavelink import Playable, QueueMode

from core import ui as cui

if TYPE_CHECKING:
    from discord import Emoji, Interaction, PartialEmoji
    from discord.ext.commands import Paginator

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
        elif itn.user == vc.privileged or itn.permissions.manage_guild:
            return True
        else:
            await itn.response.send_message("You need to be DJ to use this.", ephemeral=True)
            return False


class PlayerSkipButton(PlayerButton):
    async def interaction_check(self, itn: Interaction) -> bool:
        assert self.view is not None
        vc = self.view.vc

        if not vc.current or not vc.connected:
            await itn.response.defer()
            return False

        if itn.user not in vc.channel.members:
            await itn.response.send_message(f"You need to be in {vc.channel.mention} to use this.", ephemeral=True)
            return False
        return vc is not None and vc.current is not None


class LoopTypeSelect(ui.Select["PlayerController"]):
    def __init__(self, vc: Player, controller: PlayerController):
        self.vc = vc
        self.controller = controller
        assert vc.current is not None
        super().__init__(
            placeholder="Choose loop type...",
            options=[
                discord.SelectOption(
                    emoji="<:loop_one:1155046706774286366>",
                    label=f"Loop {vc.current.title if len(vc.current.title) <= 92 else f'{vc.current.title[:92]}...'}",
                    description="Enable loop for this track only.",
                    value="TRACK",
                ),
                discord.SelectOption(
                    emoji="<:loop_all:1155046704509374534>",
                    label="Loop the Queue",
                    description="Enable loop on the whole queue.",
                    value="QUEUE",
                ),
                discord.SelectOption(
                    emoji="<:stop:1058275420388212736>",
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
            disable = self.values[0] == "DISABLE"
            loop_queue = self.values[0] == "QUEUE"
            self.controller.loop.emoji = (
                "<:loop_all:1155046704509374534>" if loop_queue else "<:loop_one:1155046706774286366>"
            )
            self.controller.loop.style = discord.ButtonStyle.green
            if disable:
                self.vc.queue.mode = QueueMode.normal
            elif loop_queue:
                self.vc.queue.mode = QueueMode.loop_all
            else:
                self.vc.queue.mode = QueueMode.loop
            self.controller.remove_item(self)
            self.controller.choosing_loop = False
            await self.controller.update(itn)


class PlayerController(ui.View):
    def __init__(self, /, *, ctx: PlayerContext, vc: Player) -> None:
        self.ctx: PlayerContext = ctx
        self.vc: Player = vc
        self.message: discord.Message | None = None
        self.counter: int = -1
        self.is_updating: bool = False
        self.choosing_loop: bool = False
        self.update_lock: asyncio.Lock = asyncio.Lock()
        super().__init__(timeout=None)

    async def disable(self) -> None:
        self.stop()
        self.vc.controller = None
        if self.message is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await self.message.edit(view=None)

    def set_disabled(self, disabled: bool) -> None:
        self.rewind.disabled = disabled
        self.pause.disabled = disabled
        self.skip.disabled = disabled
        self.shuffle.disabled = disabled
        self.loop.disabled = disabled

    def update_buttons(self) -> None:
        self.set_disabled(False)
        self.pause.style = ButtonStyle.gray
        self.loop.style = ButtonStyle.gray
        self.loop.emoji = "<:loop_all:1155046704509374534>"

        vc = self.vc

        if self.choosing_loop:
            self.loop.disabled = True

        if vc.queue.mode is not QueueMode.normal:
            self.loop.style = ButtonStyle.green
            if vc.queue.mode == QueueMode.loop:
                self.loop.emoji = "<:loop_one:1155046706774286366>"

        if vc.paused:
            self.pause.style = ButtonStyle.red

        if len(vc.queue) <= 1:
            self.shuffle.disabled = True

        if vc.current is None:
            self.set_disabled(True)

    async def update(self, itn: Interaction | None = None) -> None:
        if self.is_updating or self.is_finished() or self.message is None:
            return
        if self.counter >= 10:
            return

        async with self.update_lock:
            self.is_updating = True
            self.update_buttons()

            if type(self.message) != discord.Message:
                try:
                    self.message = await self.message.fetch()
                except discord.HTTPException:
                    return await self.disable()

            current = self.vc.current
            embed = self.vc.create_now_playing(current)

            edit = itn.response.edit_message if itn and not itn.response.is_done() else self.message.edit
            await edit(embed=embed, view=self)
            self.is_updating = False

    @cui.button(cls=PlayerButton, emoji="<:skip_left:1058275414591684689>")
    async def rewind(self, itn: Interaction, _: PlayerButton):
        await self.vc.seek(0)
        if self.vc.paused:
            await self.vc.pause(False)
        self.ctx.bot.command_usage["seek"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerButton, emoji="<:play_or_pause:1155046709274083400>")
    async def pause(self, itn: Interaction, _: PlayerButton):
        await self.vc.pause(not self.vc.paused)
        self.ctx.bot.command_usage["pause" if not self.vc.paused else "resume"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerSkipButton, emoji="<:skip_right:1058275418987319356>")
    async def skip(self, itn: Interaction, _: PlayerSkipButton):
        vc = self.vc

        assert self.vc.current is not None

        send = itn.followup.send if itn.response.is_done() else itn.response.send_message

        if self.vc.privileged == itn.user:
            await self.vc.skip()
            await send(f"DJ {itn.user} has skipped the track.")
        elif self.vc.current.extras.requester_id == itn.user.id:
            await self.vc.skip()
            await send(f"Track requester {itn.user} has skipped the track.")
        else:
            required = math.ceil(len(vc.channel.members) / 2)
            if itn.user.id in self.vc.skip_votes:
                await send("You already voted to skip the track.", ephemeral=True)
            self.vc.skip_votes.add(itn.user.id)
            if len(self.vc.skip_votes) >= required:
                await self.vc.skip()
                await send(f"Vote to skip passed ({required} of {required}). Skipping.")
                return
            await send(f"Voted to skip. ({len(self.vc.skip_votes)}/{required})", ephemeral=True)
        self.ctx.bot.command_usage["skip"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerButton, emoji="<:shuffle:1155046707990630460>")
    async def shuffle(self, itn: Interaction, _: PlayerButton):
        vc = self.vc

        vc.queue.shuffle()
        self.ctx.bot.command_usage["queue shuffle"] += 1
        await self.update(itn)

    @cui.button(cls=PlayerButton, emoji="<:loop_all:1155046704509374534>")
    async def loop(self, itn: Interaction, button: PlayerButton):
        assert self.vc.current is not None

        self.add_item(LoopTypeSelect(self.vc, self))
        self.choosing_loop = True
        button.disabled = True
        self.ctx.bot.command_usage["queue loop"] += 1
        await self.update(itn)


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


class LyricPageSource(menus.ListPageSource):
    def __init__(self, title: str, paginator: Paginator):
        self.title = title
        super().__init__(paginator.pages, per_page=1)

    async def format_page(self, menu: menus.MenuPages, page: str) -> discord.Embed:
        return discord.Embed(title=f"{self.title} lyrics", description=page, color=0x00FFB3)
