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
import contextlib
import datetime
import difflib
import inspect
import io
import re
import sys
from importlib.metadata import distribution, packages_distributions
from typing import Annotated, Any, Callable, Generator, TYPE_CHECKING

import discord
import psutil
import toml
from discord.ext import commands
from jishaku import Feature
from jishaku.codeblocks import codeblock_converter
from jishaku.cog import OPTIONAL_FEATURES, STANDARD_FEATURES
from jishaku.exception_handling import ReplResponseReactor
from jishaku.functools import AsyncSender
from jishaku.math import natural_size
from jishaku.modules import package_version
from jishaku.repl import AsyncCodeExecutor

if TYPE_CHECKING:
    from core import Command, Context, OiBot


class ExtensionConverter(commands.Converter):
    async def convert(self, ctx: Context, extensions: str) -> list[str]:
        exts = []
        split = extensions.split()
        for extension in split:
            matches = difflib.get_close_matches(extension, ctx.bot.extensions)
            if extension in ("a", "all", "~", "*"):
                exts.extend(ctx.bot.extensions)
            elif matches:
                exts.append(matches[0])
            else:
                exts.append(extension)

        return exts


class Owner(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    """
    Jishaku and Developer commands.
    """

    bot: OiBot
    load_time: datetime.datetime
    start_time: datetime.datetime
    walk_commands: Callable[[], Generator[Command[Owner, (...), Any], None, None]]  # type: ignore

    def __init__(self, bot: OiBot):
        self.bot = bot
        super().__init__(bot=bot)  # type: ignore
        for command in self.walk_commands():
            command.hidden = True
            command.member_permissions = ["bot_owner"]

    @property
    def display_emoji(self) -> str:
        return "\U0001f6e0\U0000fe0f"

    @Feature.Command(name="jishaku", aliases=["jsk", "developer", "dev", "d"], invoke_without_command=True)
    async def jsk(self, ctx: Context):
        """
        The Jishaku debug and diagnostic commands.

        This command on its own gives a status brief.
        All other functionality is within its subcommands.
        """

        # Try to locate what vends the `discord` package
        distributions: list[str] = [
            dist
            for dist in packages_distributions()["discord"]  # type: ignore
            if any(
                file.parts == ("discord", "__init__.py")  # type: ignore
                for file in distribution(dist).files  # type: ignore
            )
        ]

        if distributions:
            dist_version = f"{distributions[0]} `{package_version(distributions[0])}`"
        else:
            dist_version = f"unknown `{discord.__version__}`"

        summary = [
            f"Jishaku v{package_version('jishaku')}, {dist_version}, "
            f"`Python {sys.version}` on `{sys.platform}`".replace("\n", ""),
            f"Module was loaded <t:{self.load_time.timestamp():.0f}:R>, "
            f"cog was loaded <t:{self.start_time.timestamp():.0f}:R>.",
            "",
        ]

        # detect if [procinfo] feature is installed
        if psutil:
            try:
                proc = psutil.Process()

                with proc.oneshot():
                    try:
                        mem = proc.memory_full_info()
                        summary.append(
                            f"Using {natural_size(mem.rss)} physical memory and "
                            f"{natural_size(mem.vms)} virtual memory, "
                            f"{natural_size(mem.uss)} of which unique to this process."
                        )
                    except psutil.AccessDenied:
                        pass

                    try:
                        name = proc.name()
                        pid = proc.pid
                        thread_count = proc.num_threads()

                        summary.append(f"Running on PID {pid} (`{name}`) with {thread_count} threads.")
                    except psutil.AccessDenied:
                        pass

                    summary.append("")  # blank line
            except psutil.AccessDenied:
                summary.append(
                    "psutil is installed, but this process does not have high enough access rights "
                    "to query process information."
                )
                summary.append("")  # blank line
        user_count = sum(g.member_count for g in self.bot.guilds if g.member_count)
        cache_summary = f"{len(self.bot.guilds)} guilds and about {user_count:,} users"

        # Show shard settings to summary
        if isinstance(self.bot, discord.AutoShardedClient):
            if len(self.bot.shards) > 20:
                summary.append(
                    f"This bot is automatically sharded ({len(self.bot.shards)} shards of {self.bot.shard_count})"
                    f" and can see {cache_summary}."
                )
            else:
                shard_ids = ", ".join(str(i) for i in self.bot.shards.keys())
                summary.append(
                    f"This bot is automatically sharded (Shards {shard_ids} of {self.bot.shard_count})"
                    f" and can see {cache_summary}."
                )
        elif self.bot.shard_count:
            summary.append(
                f"This bot is manually sharded (Shard {self.bot.shard_id} of {self.bot.shard_count})"
                f" and can see {cache_summary}."
            )
        else:
            summary.append(f"This bot is not sharded and can see {cache_summary}.")

        if self.bot._connection.max_messages:  # type: ignore
            message_cache = f"Message cache capped at {self.bot._connection.max_messages}"  # type: ignore
        else:
            message_cache = "Message cache is disabled"

        remarks = {True: "enabled", False: "disabled", None: "unknown"}

        *group, last = (
            f"{intent.replace('_', ' ')} intent is {remarks.get(getattr(self.bot.intents, intent, None))}"
            for intent in ("presences", "members", "message_content")
        )

        summary.append(f"{message_cache}, {', '.join(group)}, and {last}.")

        # Show websocket latency in milliseconds
        summary.append(f"Average websocket latency: {round(self.bot.latency * 1000, 2)}ms")

        embed = discord.Embed(title="Jishaku", description="\n".join(summary), color=0x2F3136)

        await ctx.send(embed=embed)

    async def do_extension(
        self, ctx: Context, action: Callable[..., Any], extensions: list[str]
    ) -> tuple[list[str], list[str]]:
        loaded: list[str] = []
        failed: list[str] = []
        for extension in extensions:
            try:
                await action(extension)
                loaded.append(f"<:greentick:968136930208415784> `{extension}`")
            except Exception as exc:
                failed.append(f"<:redtick:968136831105376326> `{extension}`\n```py\n{exc}\n```")

        return (loaded, failed)

    @Feature.Command(parent="jsk", name="py", aliases=["python"])
    async def jsk_python(self, ctx: Context, *, argument: codeblock_converter):  # type: ignore
        """
        Direct evaluation of Python code.
        """
        arg_dict, convertables = self.jsk_python_get_convertables(ctx)
        message_reference = getattr(ctx.message.reference, "resolved", None)
        voice_client = ctx.voice_client
        arg_dict["reference"] = message_reference
        arg_dict["ref"] = message_reference
        arg_dict["source"] = inspect.getsource
        arg_dict["vc"] = voice_client
        arg_dict["player"] = voice_client
        arg_dict["_"] = self.last_result

        out = io.StringIO()
        scope = self.scope

        try:
            async with ReplResponseReactor(ctx.message):
                with contextlib.redirect_stdout(out):
                    with self.submit(ctx):
                        executor = AsyncCodeExecutor(argument.content, scope, arg_dict=arg_dict, convertables=convertables)
                        async for send, result in AsyncSender(executor):  # type: ignore
                            send: Callable[..., None]
                            result: Any

                            if result is None and out and out.getvalue():
                                result = f"Redirected stdout\n```{out.getvalue()}```"

                            if result is None:
                                continue

                            self.last_result = result

                            send(await self.jsk_python_result_handling(ctx, result))

        finally:
            scope.clear_intersection(arg_dict)

    @Feature.Command(parent="jsk", name="load", aliases=["l"])
    async def jsk_load(self, ctx: Context, *extensions: str):
        """
        Loads extensions.
        """
        loaded, failed = await self.do_extension(ctx, self.bot.load_extension, list(extensions))

        fmtd = "\n".join(loaded + failed)
        embed = discord.Embed(title="Reloaded extensions", description=fmtd)
        await ctx.send(embed=embed)

    @Feature.Command(parent="jsk", name="unload", aliases=["u"])
    async def jsk_unload(self, ctx: Context, *, extensions: Annotated[list[str], ExtensionConverter]):
        """
        Unloads extensions.
        """
        loaded, failed = await self.do_extension(ctx, self.bot.unload_extension, extensions)

        fmtd = "\n".join(loaded + failed)
        embed = discord.Embed(title="Unloaded extensions", description=fmtd)
        await ctx.send(embed=embed)

    @Feature.Command(parent="jsk", name="reload", aliases=["r"])
    async def jsk_reload(self, ctx: Context, *, extensions: Annotated[list[str], ExtensionConverter]):
        """
        Reloads extensions.
        """
        loaded, failed = await self.do_extension(ctx, self.bot.reload_extension, extensions)

        fmtd = "\n".join(loaded + failed)
        embed = discord.Embed(title="Reloaded extensions", description=fmtd)
        await ctx.send(embed=embed)

    @Feature.Command(parent="jsk", name="maintenance")
    async def jsk_maintenance(self, ctx: Context, enabled: bool):
        """
        Enable/disable maintenance.
        """
        self.bot.maintenance = enabled
        await ctx.send(f"Maintenance Enabled: {enabled}")

    @Feature.Command(parent="jsk", name="news")
    async def jsk_news(self, ctx: Context, *, news: str):
        """
        Changes the news of the bot.
        """
        self.bot.news = news
        toml_data = toml.load("config.toml")
        with open("config.toml", "w") as f:
            toml_data["BOT_NEWS"] = news
            toml.dump(toml_data, f)
        await ctx.send(f"Bot news: {news}")

    @Feature.Command(parent="jsk", name="gitsync", aliases=["gs"])
    async def gitsync(self, ctx: Context):
        """
        Syncs with github repo and tries to reload changed extensions.
        """
        proc = await asyncio.create_subprocess_shell(
            "git pull", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        shell = ""
        if stderr:
            shell = f"[stderr]\n{stderr.decode()}"
        if stdout:
            shell = f"[stdout]\n{stdout.decode()}"

        em = discord.Embed(description=f"```sh\n$git pull\n{shell}```\n")

        changed = "".join(
            [
                item.replace("/", ".").replace(".py", "").strip()
                for item in re.findall(r".*[^\/\n]+\.py", shell, re.MULTILINE)
            ]
        )
        to_reload = await ExtensionConverter().convert(ctx, changed)

        reloaded = []
        for files in to_reload:
            if files in self.bot.extensions:
                try:
                    await self.bot.reload_extension(files)
                    reloaded.append(f"<:greentick:968136930208415784> `{files}`")
                except commands.ExtensionError as e:
                    reloaded.append(f"<:redtick:968136831105376326> `{files}`\n```py\n{e}\n```")

        if reloaded:
            em.add_field(name="Reloaded Extensions", value="\n".join(reloaded))

        await ctx.send(embed=em)


async def setup(bot: OiBot):
    await bot.add_cog(Owner(bot=bot))  # type: ignore
