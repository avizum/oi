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

import asyncio
import datetime as dt
import logging
import re
from datetime import datetime

import aiohttp
import async_timeout
import asyncpg
import discord
import jishaku
import toml
import wavelink
from discord.app_commands import AppCommand
from discord.ext import commands
from discord.ext.commands.core import _CaseInsensitiveDict
from discord.utils import _ColourFormatter
from topgg.client import DBLClient
from topgg.webhook import WebhookManager
from waifuim import Client as WaifiImClient

from extensions.logger import WebhookHandler
from utils.cache import ExpiringCache
from utils.types import Blacklist, PlayerSettings

from .commands import Bot, Cog, HybridCommand

_log = logging.getLogger("oi")

jishaku.Flags.HIDE = True
jishaku.Flags.RETAIN = True
jishaku.Flags.NO_UNDERSCORE = True
jishaku.Flags.FORCE_PAGINATOR = True
jishaku.Flags.NO_DM_TRACEBACK = True


__all__ = ("OiBot",)


class OiBot(Bot):
    user: discord.ClientUser
    webhook_handler: WebhookHandler
    pool: asyncpg.Pool
    owner_id: None
    owner_ids: set[int]

    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            allowed_mentions=discord.AllowedMentions(replied_user=False, everyone=False),
            owner_ids={
                531179463673774080,  # Rolex
                920320601615380552,  # Rolex alt
                750135653638865017,  # avizum
                343019667511574528,  # Crunchy
                857103603130302514,  # Var
            },
        )
        self._BotBase__cogs: dict[str, commands.Cog] = _CaseInsensitiveDict()
        self.votes: ExpiringCache = ExpiringCache(60 * 60 * 12)  # 12 hours
        self.maintenance: bool = False
        self.maintenance_cogs: list[Cog] = []
        self.launched_at: datetime = datetime.now(tz=dt.timezone.utc)
        self.command_usage: dict[str, int] = {}
        self.blacklisted: dict[int, Blacklist] = {}
        self.player_settings: dict[int, PlayerSettings] = {}
        self.songs_played: int = 0
        self.support_server: str = "https://discord.gg/hWhGQ4QHE9"
        self.invite_url: str = discord.utils.oauth_url(867713143366746142, permissions=discord.Permissions(1644942454270))
        self.context: type[commands.Context] = commands.Context
        self.theme: int = 0x00FFB3

        with open("config.toml", "r") as f:
            self.config = toml.loads(f.read())

        self.news = self.config.get("BOT_NEWS", "No news :fearful:")

    async def on_message(self, message: discord.Message, /):
        if re.fullmatch("<@867713143366746142>", message.content):
            em = discord.Embed(description=f"Hey, {message.author.mention}, My prefix is `/`.\n", color=0x00FFB3)
            em.set_image(
                url="https://cdn.discordapp.com/attachments/790354100654964776/1015124745689239592/how_to_slash.png"
            )
            await message.channel.send(embed=em)
        await self.process_commands(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message, /):
        if before.content == after.content:
            return
        await self.process_commands(after)

    async def get_context(
        self, origin: discord.Message | discord.Interaction, *, cls: type[commands.Context] | None = None
    ) -> commands.Context:
        return await super().get_context(origin, cls=cls or self.context)

    async def on_ready(self) -> None:
        _log.info(f"Logged in. {self.user} ({self.user.id})")

    async def start_wavelink_nodes(self) -> None:
        await self.wait_until_ready()

        try:
            with async_timeout.timeout(15):
                nodes: list[wavelink.Node] = [wavelink.Node(**self.config["LAVALINK"])]
                await wavelink.Pool.connect(nodes=nodes, client=self)
                _log.info("Started Lavalink node.")
        except asyncio.TimeoutError:
            _log.exception("Creating a Lavalink node timed out.")

    async def start_waifuim(self) -> None:
        await self.wait_until_ready()

        self.waifuim = WaifiImClient(
            token=self.config["WAIFUIM_TOKEN"], session=aiohttp.ClientSession(), identifier=f"OiBot|{self.user.id}"
        )

    async def start_topgg(self) -> None:
        post = True
        interval = 3600
        if self.user.id != 867713143366746142:
            post = False
            interval = None

        await self.wait_until_ready()

        self.topgg = DBLClient(
            self, token=self.config["TOPGG_TOKEN"], autopost=post, post_shard_count=post, autopost_interval=interval
        )

        self.topgg_webhook = WebhookManager(self).dbl_webhook("/topgg", auth_key=self.config["TOPGG_AUTH"])
        await self.topgg_webhook.run(2832)

    async def load_extensions(self) -> None:
        extensions: tuple[str, ...] = (
            "core.context",
            "extensions.logger",
            "extensions.listeners",
            "extensions.error_handler",
            "extensions.cogs.owner",
            "extensions.cogs.help",
            "extensions.cogs.moderation",
            "extensions.cogs.utility",
            "extensions.cogs.music",
            "extensions.cogs.images",
            "extensions.cogs.fun",
            "extensions.cogs.support",
        )
        for extension in extensions:
            try:
                await self.load_extension(extension)

                _log.info(f"Loaded extension: {extension}")
            except Exception as e:
                _log.exception(f"Failed to load extension: {extension}. {e}")

        owner = self.get_cog("Owner")
        for command in self.walk_commands():
            if command.cog == owner:
                continue
            if command.qualified_name in self.command_usage:
                continue
            self.command_usage[command.qualified_name] = 0

    async def fill_command_mentions(self, commands: list[AppCommand] | None = None) -> None:
        await self.wait_until_ready()
        raw_tree_cmds = commands or await self.tree.fetch_commands()
        for raw_cmd in raw_tree_cmds:
            cmd = self.get_command(raw_cmd.name)
            if isinstance(cmd, HybridCommand):
                cmd.raw_app_command = raw_cmd

    async def create_pool(self) -> asyncpg.Pool:
        pool: asyncpg.Pool = await asyncpg.create_pool(**self.config["POSTGRESQL"])  # type: ignore
        blacklisted = await pool.fetch("SELECT * FROM blacklist")
        for data in blacklisted:
            self.blacklisted[data["user_id"]] = dict(data)  # type: ignore

        player_settings = await pool.fetch("SELECT * FROM player_settings")
        for data in player_settings:
            self.player_settings[data["guild_id"]] = dict(data)  # type: ignore

        self.pool = pool
        return pool

    def setup_logging(self) -> None:
        formatter = _ColourFormatter()
        handler = WebhookHandler()
        handler.setFormatter(formatter)
        self.webhook_handler = handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.addHandler(stream_handler)
        logger.setLevel(logging.INFO)

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self.loop.create_task(self.load_extensions())
        self.loop.create_task(self.create_pool())
        self.loop.create_task(self.start_wavelink_nodes())
        self.loop.create_task(self.start_topgg())
        self.loop.create_task(self.start_waifuim())
        self.loop.create_task(self.fill_command_mentions())

    def run(self) -> None:
        self.setup_logging()
        super().run(self.config["BOT_TOKEN"], reconnect=True, log_handler=None)

    async def close(self):
        _log.info("Logging out.")
        await self.session.close()
        await super().close()
