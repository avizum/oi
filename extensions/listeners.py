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

import difflib
import logging
import random
from typing import TYPE_CHECKING, TypedDict

import asyncpg
import discord
import humanize
from discord.ext import commands, tasks

import core
from utils import ANSIFormat, Blacklisted, embed_to_text, Maintenance

if TYPE_CHECKING:
    from core import Context, OiBot


# This is needed because the bot has no intents.
# Bot.get_user always returns None.
MODS = {
    531179463673774080: "rolex6596",  # Rolex
    920320601615380552: "rolex4160",  # Rolex alt
    750135653638865017: "avizum",  # avizum
    343019667511574528: "crunchyanime",  # Crunchy
}

_log = logging.getLogger(__name__)


class CommandData(TypedDict):
    command_name: str
    guild_id: int
    channel_id: int
    user_id: int
    used: str
    app_command: bool
    success: bool


class Important(core.Cog):
    def __init__(self, bot: OiBot) -> None:
        self.bot: OiBot = bot
        self.vote_webhook: discord.Webhook = discord.Webhook.from_url(bot.config["VOTE_WEBHOOK"], session=bot.session)
        self.guilds_webhook: discord.Webhook = discord.Webhook.from_url(bot.config["GUILDS_WEBHOOK"], session=bot.session)
        self._command_queue: list[CommandData] = []

    async def cog_load(self) -> None:
        await self.bot.wait_until_ready()
        self.update_status.start()
        self.insert_queue.add_exception_type(asyncpg.PostgresConnectionError)
        self.insert_queue.start()

    async def cog_unload(self) -> None:
        self.update_status.cancel()
        self.insert_queue.cancel()

    async def bot_check(self, ctx: Context) -> bool:
        if await self.bot.is_owner(ctx.author):
            return True
        if ctx.author.id in self.bot.cache.blacklisted:
            entry = self.bot.cache.blacklisted[ctx.author.id]
            raise Blacklisted(moderator=MODS[entry["moderator"]], reason=entry["reason"], permanent=entry["permanent"])
        if ctx.guild is None:
            raise commands.NoPrivateMessage("Commands can not be used in DMs.")
        if self.bot.maintenance and not await self.bot.is_owner(ctx.author):
            raise Maintenance("Bot is under maintenance.")
        if ctx.cog in self.bot.maintenance_cogs:
            raise Maintenance(f"{ctx.cog.qualified_name} module is under maintenance.")
        return True

    @tasks.loop(minutes=5)
    async def update_status(self) -> None:
        guilds = len(self.bot.guilds)
        for shard in self.bot.shards:
            activities = [
                f"Shard {shard} | {guilds:,} Servers",
                f"{len(self.bot.voice_clients):,} Songs Playing",
                f"Up for {humanize.precisedelta(discord.utils.utcnow() - self.bot.launched_at, minimum_unit='hours')}",
                f"{self.bot.songs_played} songs played",
                "Made by @rolex6596 and @avizum",
            ]
            activity = discord.CustomActivity(name=random.choice(activities))
            await self.bot.change_presence(activity=activity, shard_id=shard)

    @tasks.loop(seconds=10)
    async def insert_queue(self) -> None:
        query = """
            INSERT INTO command_usage (command_name, guild_id, channel_id, user_id, used, app_command, success)
            SELECT c.command_name, c.guild_id, c.channel_id, c.user_id, c.used, c.app_command, c.success
            FROM jsonb_to_recordset($1::jsonb) AS c(
                command_name TEXT,
                guild_id BIGINT,
                channel_id BIGINT,
                user_id BIGINT,
                used TIMESTAMP,
                app_command BOOLEAN,
                success BOOLEAN
            )
        """
        if self._command_queue:
            await self.bot.pool.execute(query, self._command_queue)
            self._command_queue.clear()

    @core.Cog.listener()
    async def on_command(self, ctx: Context) -> None:
        self.log_command(ctx)

    def log_command(self, ctx: Context):
        command = ctx.command
        try:
            if "bot_owner" in command.member_permissions:
                return
        except AttributeError:
            member_permisions = command.extras.get("member_permissions", [])
            if "bot_owner" in member_permisions:
                return

        if isinstance(ctx.command, core.HybridGroup):
            if not ctx.command.fallback:
                # We don't need to log commands without a fallback because commands without fallback have no functionality
                # other than sending the help command for the group.
                return

        command_name = command.qualified_name
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        used = ctx.message.created_at.isoformat()
        app_command = ctx.prefix in ["/", "\u200b"]
        success = not ctx.command_failed

        self.bot.command_usage[command_name] += 1

        _ = ANSIFormat
        if ctx.interaction:
            namespace = ctx.interaction.namespace
            params = [f"{_(f"{i[0]}:"):*;d} {i[1]}" for i in namespace]
            message = f"{_(f"/{command_name}"):**} {" ".join(params)}"
        else:
            message = ctx.message.content.replace(
                f"{ctx.prefix}{command_name}", f"{_(f"{ctx.clean_prefix}{command_name}"):**}"
            )

        _log.info(f"{ctx.author} ({user_id}) #{ctx.channel.name} ({guild_id}): {message}")

        self._command_queue.append(
            {
                "command_name": command_name,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "used": used,
                "app_command": app_command,
                "success": success,
            }
        )

    @core.Cog.listener()
    async def on_dbl_vote(self, data: dict) -> None:
        if data["type"] == "test":
            return self.bot.dispatch("dbl_test", data)

        user_id = int(data["user"])
        user = await self.bot.fetch_user(user_id)

        self.bot.votes[user_id] = True

        embed = discord.Embed(title="Vote Received", description=f"User: {user} (ID: {user_id})", color=self.bot.theme)
        await self.vote_webhook.send(embed=embed)

        embed.description = "Thank you for voting for Oi!\nPlease vote again in 12 hours."

        embed.set_image(url="https://media.discordapp.net/attachments/890645724243558431/934771253036867644/thanksvote.gif")
        await user.send(embed=embed)

    @core.Cog.listener()
    async def on_dbl_test(self, data: dict) -> None:
        user = self.bot.fetch_user(int(data["user"]))
        await user.send("Test vote received.")

    @core.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        embed = discord.Embed(
            title="Joined Guild",
            description=(f"Name: {guild.name} | {guild.id}\n" f"Owner: {guild.owner_id}\n" f"Members: {guild.member_count}"),
            color=discord.Color.green(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Now in {len(self.bot.guilds)} guilds")
        await self.guilds_webhook.send(username="Oi: Joined Guild", embed=embed)

        channels = [
            channel
            for channel in guild.text_channels
            if channel.permissions_for(guild.me).send_messages
            and channel.permissions_for(guild.me).embed_links
            and difflib.get_close_matches(channel.name, ["general", "chat", "main"])
        ]

        channel = channels[0] if channels else guild.system_channel or guild.text_channels[0]

        embed = discord.Embed(
            title="Hello, I am Oi!",
            description=(
                "Thank you for adding me to your server.\n"
                "I have a lot of commands that can liven the server.\n"
                "You can view all of my commands by using /help.\n"
                f"If you have any probelms, you can visit the [support server]({self.bot.support_server}).\n"
            ),
            color=0x00FFB3,
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Sorry if this disrupted something, you may delete this message. :)")

        bot_permissions = channel.permissions_for(guild.me)
        if bot_permissions.send_messages:
            if not bot_permissions.embed_links:
                await channel.send(embed_to_text(embed))
                return
            await channel.send(embed=embed)
            return

    @core.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        if guild.owner is None or guild.members is None:
            return
        embed = discord.Embed(
            title="Left Guild",
            description=(f"Name: {guild.name} | {guild.id}\n" f"Owner: {guild.owner_id}\n" f"Members: {guild.member_count}"),
            color=discord.Color.red(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Now in {len(self.bot.guilds)} guilds")
        await self.guilds_webhook.send(username="Oi: Left Guild", embed=embed)


async def setup(bot: OiBot) -> None:
    await bot.add_cog(Important(bot))
