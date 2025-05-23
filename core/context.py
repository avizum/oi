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

import contextlib
import random
import sys
from typing import Any, Generic, Sequence, TYPE_CHECKING, TypeVar

import discord
from discord.ext import commands
from discord.utils import MISSING

from utils import embed_to_text, OiView
from utils.helpers import _format_embeds

if TYPE_CHECKING:
    from .commands import CommandGroupUnion
    from .oi import OiBot

BotT = TypeVar("BotT", bound=commands.Bot | commands.AutoShardedBot)


__all__ = (
    "ConfirmResult",
    "Context",
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


def get_tip() -> list[str]:
    tips: list[list[str]] = [
        [
            random.choice(
                [
                    "Please vote for Oi. \U0001f97a\U0001f97a\U0001f97a",
                    "Oi is free to use, please vote to support Oi. Thank you \U00002764\U0000fe0f.",
                    "<:cr_ztheart:853385258762240041> Voting helps support Oi.",
                    "<:cr_ztheart:853385258762240041> If you vote for Oi, you might get a cookie!",
                    "Please Please Please vote for Oi!!",
                    "Why haven't you voted for Oi? Do it now!",
                    "These messages will go away for 12 hours if you vote for Oi.",
                    "Voting for Oi will help us grow!",
                ]
            ),
            "Vote Here!",
            "https://top.gg/bot/867713143366746142/vote",
        ],
        [
            random.choice(
                [
                    "Join the support server if you need help!",
                    "Need Help? Use `/help` or join the support server!",
                    "Have some feedback for us? Join the support server and send it our way.",
                    "If you need to report a bug, report it in the support server.",
                    "Create your own playlists with </playlist create:1301780161410371647>",
                ]
            ),
            "Support Server",
            "https://discord.gg/hWhGQ4QHE9",
        ],
        [
            "Oi is made by people on their free time! Check out avizum's page!",
            "avizum's page",
            "https://github.com/avizum",
        ],
        [
            "Oi is made by people on their free time! Check out ROLEX's page!",
            "ROLEX's page",
            "https://github.com/Shobhits7",
        ],
    ]
    return random.choices(tips, [6, 4, 1, 1], k=1)[0]


CHANCE = 3 / 20


class Context(commands.Context, Generic[BotT]):
    bot: OiBot
    author: discord.Member
    guild: discord.Guild
    command: CommandGroupUnion
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
        no_tips: bool = False,
        mention_author: bool | None = None,
        format_embeds: bool = True,
        view: discord.ui.View | None = None,
        suppress_embeds: bool = False,
        ephemeral: bool = False,
        silent: bool = False,
        poll: discord.Poll = MISSING,
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
                msg = "-# *I need the `Embed Links` permission to send embeds. [Why?](https://gist.github.com/avizum/827fd8015a0605e68b5966ff5b2b449f)*"
                new = "\n".join(embed_to_text(emb) for emb in embeds)
                content = f"{content}\n{new}\n{msg}" if content else f"{new}\n{msg}"
            embeds = None
            embed = None

        reference = self.message.to_reference(fail_if_not_exists=False) if reply else reference
        if not self.permissions.read_message_history:
            reference = None

        random_float = random.random()
        fmt_content = content
        message = ""

        if self.author.id in self.bot.thanked_votes and not no_tips:
            timestamp = self.bot.thanked_votes[self.author.id]
            label = "Vote Here"
            url = "https://top.gg/bot/867713143366746142/vote"
            if discord.utils.utcnow() > timestamp:
                message = "Thank you for voting for Oi. It's time to vote again!"
            else:
                message = f"Thank you for voting for Oi. Please vote again {discord.utils.format_dt(timestamp, "R")}."
            del self.bot.thanked_votes[self.author.id]

        if self.author.id not in self.bot.votes and random_float < CHANCE and not no_tips:
            message, label, url = get_tip()

        if message:
            fmt = f"-# {message} | <{url}>"
            fmt_content = f"{content}\n{fmt}" if content is not None else fmt

        if self.interaction is None or self.interaction.is_expired():
            return await super().send(
                content=fmt_content,
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
                poll=poll,
            )  # type: ignore # Implementation supports this

        # Convert None to MISSING to appease type remaining implementations
        kwargs = {
            "content": content,
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
            "poll": poll,
        }

        if self.interaction and not self.channel.permissions_for(self.me).send_messages:
            msg = "-# *I need the `Send Messages` permission in this channel. [Why?](https://gist.github.com/avizum/827fd8015a0605e68b5966ff5b2b449f)*"
            kwargs["content"] = f"{kwargs['content']}\n{msg}" if kwargs["content"] else msg

        if self.interaction.response.is_done():
            msg = await self.interaction.followup.send(**kwargs, wait=True)
        else:
            await self.interaction.response.send_message(**kwargs)
            msg = await self.interaction.original_response()

        if delete_after is not None:
            await msg.delete(delay=delete_after)

        with contextlib.suppress():
            if message and label and url:
                view = discord.ui.View()
                view.add_item(discord.ui.Button(style=discord.ButtonStyle.url, label=label, url=url))
                await self.interaction.followup.send(message, view=view, ephemeral=True)

        return msg

    async def confirm(
        self,
        *,
        message: str | None = None,
        embed: discord.Embed | None = None,
        confirm_messsage: str = 'Press "yes" to accept, or press "no" to deny',
        timeout: int = 60,  # noqa: ASYNC109
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
        if (embed and message) or embed:
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

    async def defer(self, *, ephemeral: bool = False):
        if self.interaction:
            if self.interaction.response.is_done():
                return
            await self.interaction.response.defer(ephemeral=ephemeral)


async def setup(bot: OiBot) -> None:
    bot.context = Context


async def teardown(bot: OiBot) -> None:
    bot.context = commands.Context
