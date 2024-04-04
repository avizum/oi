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
import random
import sys
from typing import Any, Generic, Sequence, TYPE_CHECKING, TypeVar

import discord
from discord.ext import commands
from discord.utils import MISSING

from utils.helpers import _format_embeds, embed_to_text
from utils.view import OiView

if TYPE_CHECKING:
    from .oi import OiBot

BotT = TypeVar("BotT", bound=commands.Bot | commands.AutoShardedBot)


__all__ = (
    "Context",
    "ConfirmResult",
)


class ConfirmView(OiView):
    def __init__(self, *, members: list[discord.Member | discord.User], timeout: int = 180):
        super().__init__(members=members, timeout=timeout)
        self.value: bool | None = None
        self.message: discord.Message | None = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, itn: discord.Interaction, _: discord.ui.Button):
        await itn.response.defer()
        self.value = True
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, itn: discord.Interaction, _):
        await itn.response.defer()
        self.value = False
        self.stop()


class ConfirmResult:
    def __init__(self, message: discord.Message, result: bool | None):
        self.message: discord.Message = message
        self.result: bool | None = result

    def __repr__(self):
        return f"<ConfirmResult result={self.result}>"


TIPS: list[list[str]] = [
    [
        "<:cr_ztheart:853385258762240041> Please vote for Oi.",
        "Vote Here!",
        "https://top.gg/bot/867713143366746142/vote",
    ],
    [
        "<:cr_ztheart:853385258762240041> These tips disappear if you vote!",
        "Vote Here!",
        "https://top.gg/bot/867713143366746142/vote",
    ],
    [
        "<:cr_ztheart:853385258762240041> If you vote for Oi, you get a cookie!",
        "Vote Here!",
        "https://top.gg/bot/867713143366746142/vote",
    ],
    ["Join the support server if you need help!", "Support Server", "https://discord.gg/hWhGQ4QHE9"],
    [
        "Need Help? Use `/help` or join the support server!",
        "Support Server",
        "https://discord.gg/hWhGQ4QHE9",
    ],
    [
        "Oi is made by people on their free time! Please be patient with us.",
        "[Developer] avizum's page",
        "https://github.com/avizum",
    ],
    [
        "Oi is made by people on their free time! Please be patient with us.",
        "[Developer] ROLEX's page",
        "https://github.com/Shobhits7",
    ],
]

CHANCE = 1 / 20


class Context(commands.Context, Generic[BotT]):
    bot: OiBot
    author: discord.Member
    guild: discord.Guild
    command: commands.Command
    me: discord.Member
    channel: discord.TextChannel | discord.VoiceChannel | discord.Thread

    @property
    def guild_permissions(self) -> discord.Permissions:
        return self.author.guild_permissions

    @property
    def bot_guild_permissions(self) -> discord.Permissions:
        return self.guild.me.guild_permissions

    async def no_reply(self, *args, **kwargs):
        return await super().send(*args, **kwargs)

    async def send(
        self,
        content: str | None = None,
        *,
        tts: bool = False,
        embed: discord.Embed | None = None,
        embeds: Sequence[discord.Embed] | None = None,
        file: discord.File | None = None,
        files: Sequence[discord.File] | None = None,
        stickers: Sequence[discord.GuildSticker | discord.StickerItem] | None = None,
        delete_after: float | None = None,
        nonce: str | int | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        reference: discord.Message | discord.MessageReference | discord.PartialMessage | None = None,
        reply: bool = True,
        mention_author: bool | None = None,
        format_embeds: bool = True,
        view: discord.ui.View | None = None,
        suppress_embeds: bool = False,
        no_tips: bool = False,
        ephemeral: bool = False,
        silent: bool = False,
    ) -> discord.Message:
        if content:
            content = str(content)
            for path in sys.path:
                content = content.replace(path, "[path]")

        if embed and embeds:
            raise ValueError("Cannot pass both embed and embeds.")

        if embed and embeds is None:
            embeds = [embed]

        if embeds:
            embeds = _format_embeds(self, embeds) if format_embeds else embeds
            embed = None

        new_perms = None
        if self.interaction and self.interaction.is_expired():
            new_perms = self.channel.permissions_for(self.me)
            self.bot_permissions = new_perms  # type: ignore

        if not self.bot_permissions.embed_links:
            if embeds:
                msg = "*I need the `Embed Links` permission to send embeds.*"
                new = "\n".join(embed_to_text(emb) for emb in embeds)
                content = f"{content}\n{new}\n\n{msg}" if content else f"{new}\n{msg}"
            embeds = None
            embed = None

        reference = self.message.to_reference(fail_if_not_exists=False) if reply else reference
        if not self.permissions.read_message_history:
            reference = None

        random_num = random.random()
        new_content = content
        original = content
        if self.author.id not in self.bot.votes and random_num < CHANCE and not no_tips:
            msg, _, url = random.choice(TIPS)
            advert = f"{msg} | <{url}>"
            new_content = f"{advert}\n\n{content}" if content is not None else advert

        if self.interaction is None or self.interaction.is_expired():
            return await super().send(
                content=new_content,
                tts=tts,
                embed=embed,
                embeds=embeds,
                file=file,
                files=files,
                stickers=stickers,
                delete_after=delete_after,
                nonce=nonce,
                allowed_mentions=allowed_mentions,
                reference=reference,
                mention_author=mention_author,
                view=view,
                suppress_embeds=suppress_embeds,
                silent=silent,
            )  # type: ignore # Implementation supports this

        # Convert None to MISSING to appease type remaining implementations
        kwargs = {
            "content": original,
            "tts": tts,
            "embed": MISSING if embed is None else embed,
            "embeds": MISSING if embeds is None else embeds,
            "file": MISSING if file is None else file,
            "files": MISSING if files is None else files,
            "allowed_mentions": MISSING if allowed_mentions is None else allowed_mentions,
            "view": MISSING if view is None else view,
            "suppress_embeds": suppress_embeds,
            "ephemeral": ephemeral,
            "silent": silent,
        }

        if self.interaction and not self.channel.permissions_for(self.me).send_messages:
            msg = "*Please give the `Send Messages` permission.*"
            kwargs["content"] = f"{kwargs['content']}\n{msg}" if kwargs["content"] else msg

        if self.interaction.response.is_done():
            msg = await self.interaction.followup.send(**kwargs, wait=True)
        else:
            await self.interaction.response.send_message(**kwargs)
            msg = await self.interaction.original_response()

        if delete_after is not None:
            await msg.delete(delay=delete_after)

        with contextlib.suppress(Exception):
            if self.author.id not in self.bot.votes and random_num < CHANCE and not no_tips:
                message, label, url = random.choice(TIPS)
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label=label, url=url))
                await self.interaction.followup.send(message, view=view, ephemeral=True)
        return msg

    async def confirm(
        self,
        *,
        message: str | None = None,
        embed: discord.Embed | None = None,
        confirm_messsage: str = 'Press "yes" to accept, or press "no" to deny',
        timeout: int = 60,
        delete_message_after: bool = False,
        remove_view_after: bool = False,
        no_reply: bool = False,
        ephemeral: bool = False,
        allowed: list[discord.Member | discord.User] | None = None,
        **kwargs: Any,
    ) -> ConfirmResult:
        if allowed is None:
            allowed = [self.author]
        if delete_message_after and remove_view_after:
            raise ValueError("Cannot have both delete_message_after and remove_view_after keyword arguments.")
        if embed and message or embed:
            embed.description = f"{embed.description}\n\n{confirm_messsage}" if embed.description else confirm_messsage
        elif message:
            message = f"{message}\n\n{confirm_messsage}"
        view = ConfirmView(members=allowed, timeout=timeout)
        msg = await self.send(content=message, embed=embed, reply=not no_reply, ephemeral=ephemeral, view=view, **kwargs)
        view.message = msg
        await view.wait()
        if delete_message_after:
            await msg.delete()
        if remove_view_after:
            await msg.edit(view=None)
        return ConfirmResult(msg, view.value)


async def setup(bot: OiBot) -> None:
    bot.context = Context


async def teardown(bot: OiBot) -> None:
    bot.context = commands.Context
