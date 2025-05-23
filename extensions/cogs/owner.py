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

import asyncio
import contextlib
import datetime
import difflib
import inspect
import io
import itertools
import re
import sys
from importlib.metadata import distribution, packages_distributions
from typing import Any, Callable, Generator, TYPE_CHECKING

import discord
import psutil
import toml
import wavelink
from discord.ext import commands
from discord.ext.commands import flag
from jishaku import Feature
from jishaku.codeblocks import codeblock_converter
from jishaku.cog import OPTIONAL_FEATURES, STANDARD_FEATURES
from jishaku.exception_handling import ReplResponseReactor
from jishaku.functools import AsyncSender
from jishaku.math import natural_size
from jishaku.modules import package_version
from jishaku.repl import AsyncCodeExecutor

from utils import BlacklistRecord

from .music.cog import SEARCH_TYPES
from .music.player import Player

if TYPE_CHECKING:
    from core import Command, Context, OiBot

    from .music import Music


class ExtensionConverter(list[str]):
    @classmethod
    async def convert(cls, ctx: Context, extension: str) -> list[str]:
        exts = []
        matches = difflib.get_close_matches(extension, ctx.bot.extensions)
        if extension.startswith(("a", "all", "i", "initial")):
            exts.extend(ctx.bot.initial_extensions)
            if extension.endswith("*"):
                exts.extend(ctx.bot.core_extensions)
        elif matches:
            exts.append(matches[0])
        else:
            exts.append(extension)
        return exts


class BlacklistFlags(commands.FlagConverter):
    reason: str = flag(description="The reason that will be displayed to the user", converter=commands.Range[str, 1, 1000])
    permanent: bool = flag(description="Whether the blacklist will be appealable.")


class ConfigFlags(commands.FlagConverter):
    po_token: str | None = flag(description="Set YouTube po token", default=None)
    visitor_data: str | None = flag(description="Set YouTube visitor data", default=None)
    refresh_token: str | None = flag(description="Set YouTube refresh token.", default=None)
    client_id: str | None = flag(description="Set Spotify client ID", default=None)
    client_secret: str | None = flag(description="Set Spotify client secret", default=None)
    sp_dc: str | None = flag(description="Set Spotify spDc cookie", default=None)
    media_api_token: str | None = flag(description="Set Apple Music media API token", default=None)


config_mapping_sources: dict[str, str] = {
    "client_id": "spotify",
    "client_secret": "spotify",
    "sp_dc": "spotify",
    "media_api_token": "applemusic",
}

config_mapping_names: dict[str, str] = {
    "po_token": "poToken",
    "visitor_data": "visitorData",
    "refresh_token": "refreshToken",
    "client_id": "clientId",
    "client_secret": "clientSecret",
    "sp_dc": "spDc",
    "media_api_token": "mediaAPIToken",
}


class Owner(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    """Jishaku and Developer commands."""

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
        self._players_to_restore: dict[int, Player] = {}

    @property
    def display_emoji(self) -> str:
        return "\U0001f6e0\U0000fe0f"

    @Feature.Command(name="jishaku", aliases=["jsk", "developer", "dev", "d"], invoke_without_command=True)
    async def jsk(self, ctx: Context):
        """The Jishaku debug and diagnostic commands.

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
                shard_ids = ", ".join(str(i) for i in self.bot.shards)
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

    async def do_extension(self, action: Callable[..., Any], extensions: list[str]) -> tuple[list[str], list[str]]:
        loaded: list[str] = []
        failed: list[str] = []
        for extension in extensions:
            try:
                await action(extension)
                loaded.append(f"<:green_tick:1294459924218384384> `{extension}`")
            except Exception as exc:
                failed.append(f"<:red_tick:1294459715266547742> `{extension}`\n```py\n{exc}\n```")

        return (loaded, failed)

    @Feature.Command(parent="jsk", name="py", aliases=["python"])
    async def jsk_python(self, ctx: Context, *, argument: codeblock_converter):  # type: ignore
        """Direct evaluation of Python code."""
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
                                result = f"Redirected stdout\n```{out.getvalue()}```"  # noqa: PLW2901

                            if result is None:
                                continue

                            self.last_result = result

                            send(await self.jsk_python_result_handling(ctx, result))

        finally:
            scope.clear_intersection(arg_dict)

    @Feature.Command(parent="jsk", name="load", aliases=["l"])
    async def jsk_load(self, ctx: Context, *extensions: str):
        """Loads extensions."""
        loaded, failed = await self.do_extension(self.bot.load_extension, [*extensions])

        fmtd = "\n".join(loaded + failed)
        embed = discord.Embed(title="Loaded extensions", description=fmtd)
        await ctx.send(embed=embed)

    @Feature.Command(parent="jsk", name="unload", aliases=["u"])
    async def jsk_unload(self, ctx: Context, extensions: commands.Greedy[ExtensionConverter]):
        """Unloads extensions."""
        loaded, failed = await self.do_extension(self.bot.unload_extension, list(itertools.chain.from_iterable(extensions)))

        fmtd = "\n".join(loaded + failed)
        embed = discord.Embed(title="Unloaded extensions", description=fmtd)
        await ctx.send(embed=embed)

    @Feature.Command(parent="jsk", name="reload", aliases=["r"])
    async def jsk_reload(self, ctx: Context, extensions: commands.Greedy[ExtensionConverter]):
        """Reloads extensions."""

        loaded, failed = await self.do_extension(self.bot.reload_extension, list(itertools.chain.from_iterable(extensions)))

        fmtd = "\n".join(loaded + failed)
        embed = discord.Embed(title="Reloaded extensions", description=fmtd)
        await ctx.send(embed=embed)

    @Feature.Command(parent="jsk", name="maintenance")
    async def jsk_maintenance(self, ctx: Context, enabled: bool):
        """Enables or disables global maintenance mode."""
        self.bot.maintenance = enabled
        await ctx.send(f"Maintenance Enabled: {enabled}")

    @Feature.Command(parent="jsk_maintenance", name="cog", aliases=["extension", "ext", "module"])
    async def jsk_maintenance_cog(self, ctx: Context, cog: str):
        """Enables or disables maintenace mode for a certain cog."""
        get_cog = self.bot.get_cog(cog)
        if not get_cog:
            return await ctx.send("Could not find cog.")
        self.bot.maintenance_cogs.append(get_cog)  # type: ignore
        return await ctx.send(f"Added {get_cog.qualified_name} to the list of maintenance cogs.")

    @Feature.Command(parent="jsk", name="news")
    async def jsk_news(self, ctx: Context, *, news: str):
        """Changes the news of the bot."""
        self.bot.news = news
        toml_data = toml.load("config.toml")
        with open(  # noqa: ASYNC230  # this operation doesn't take long, and is only called every so often.
            "config.toml", "w"
        ) as f:
            toml_data["BOT_NEWS"] = news
            toml.dump(toml_data, f)
        await ctx.send(f"Bot news: {news}")

    @Feature.Command(parent="jsk", name="blacklist")
    async def blacklist(self, ctx: Context):
        """Show the blacklisted users of the bot."""

    @Feature.Command(parent="blacklist", name="add", aliases=["a"])
    async def blacklist_add(self, ctx: Context, user: discord.User, *, flags: BlacklistFlags):
        """Adds a user to the global blacklist."""
        if user.id in self.bot.owner_ids:
            return await ctx.send("Can not blacklist Owners.")
        if user.id in self.bot.cache.blacklisted:
            return await ctx.send("User already blacklisted.")

        query = """
            INSERT INTO blacklist (user_id, reason, moderator, permanent)
            VALUES ($1, $2, $3, $4)
            RETURNING user_id, reason, moderator, permanent
        """
        data = await self.bot.pool.fetchrow(
            query, user.id, flags.reason, ctx.author.id, flags.permanent, record_class=BlacklistRecord
        )
        self.bot.cache.blacklisted[user.id] = dict(data)  # type: ignore

        embed = discord.Embed(title="You are now blacklisted from Oi", color=discord.Color.red())
        embed.add_field(
            name=f"Moderator Note from {ctx.author}:",
            value=flags.reason,
            inline=False,
        )
        if flags.permanent:
            next_steps = "This action is **PERMANENT** and can not be appealed in the support server."
        else:
            next_steps = "You may appeal this blacklist in the support server."
        embed.add_field(name="Next Steps", value=next_steps, inline=False)

        failed = "User was notified successfully."
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            failed = "Notifying the user failed."

        return await ctx.send(f"{user} added to the blacklist. {failed}")

    @Feature.Command(parent="blacklist", name="remove", aliases=["r", "rm"])
    async def blacklist_remove(self, ctx: Context, user: discord.User, *, reason: str):
        """Removes a user from the global blacklist."""
        if user.id not in self.bot.cache.blacklisted:
            return await ctx.send("User is not blacklisted.")

        blacklist = self.bot.cache.blacklisted[user.id]

        if blacklist["permanent"]:
            conf = await ctx.confirm(
                message=f"This user's blacklist was marked permanent.\n\nReason:\n>>> {blacklist["reason"]}",
                confirm_messsage=f"Do you still want to unblacklist {user}?",
            )
        else:
            conf = await ctx.confirm(message=f"Are you sure you want to unblacklist {user}?")

        if not conf.result:
            return await conf.message.edit(content="Blacklist will not be removed.", view=None)

        query = """
            DELETE FROM blacklist
            WHERE user_id = $1
        """
        await self.bot.pool.execute(query, user.id)
        del self.bot.cache.blacklisted[user.id]

        embed = discord.Embed(title="You are no longer blacklisted from Oi", color=discord.Color.green())
        embed.add_field(name=f"Moderator Note from {ctx.author}", value=reason, inline=False)
        embed.add_field(name="Next Steps", value="You may now use Oi as normal. Have Fun.", inline=False)

        failed = "User was notified successfully."
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            failed = "Notifying the user failed."

        return await conf.message.edit(content=f"{user} remove from the blacklist. {failed}", view=None)

    @Feature.Command(parent="jsk", name="gitsync", aliases=["gs"])
    async def gitsync(self, ctx: Context):
        """Syncs with github repo and tries to reload changed extensions."""
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
                    reloaded.append(f"<:green_tick:1294459924218384384> `{files}`")
                except commands.ExtensionError as e:
                    reloaded.append(f"<:red_tick:1294459715266547742> `{files}`\n```py\n{e}\n```")

        if reloaded:
            em.add_field(name="Reloaded Extensions", value="\n".join(reloaded))

        await ctx.send(embed=em)

    @Feature.Command(parent="jsk", name="music", aliases=["m"], invoke_without_command=True)
    async def jsk_music(self, ctx: Context):
        """Controls Lavalink and other music stuff."""
        node_cmd = self.bot.get_command("node")
        if not node_cmd:
            return

        await node_cmd.can_run(ctx)
        await node_cmd.invoke(ctx)

    @Feature.Command(parent="jsk_music", name="reconnect")
    async def jsk_music_reconnect(self, ctx: Context):
        """Reconnects all players."""
        cog: Music | None = self.bot.get_cog("Music")  # type: ignore
        if not cog:
            return await ctx.send("Music cog isn't loaded.")
        if not self.bot.voice_clients:
            return await ctx.send("There are no music players connected.")

        msg = await ctx.send("Reconnecting players...")
        to_reconnect: list[asyncio.Task] = [self.bot.loop.create_task(cog._reconnect(vc)) for vc in self.bot.voice_clients]  # type: ignore

        gather = await asyncio.gather(*to_reconnect)
        failed = len([result for result in gather if result is False])
        if failed:
            return await msg.edit(content=f"{failed} of {len(gather)} players failed to reconnect.")
        return await msg.edit(content="Finished reconnecting all players.")

    @Feature.Command(parent="jsk_music", name="disconnect")
    async def jsk_music_disconnect(self, ctx: Context, *, message: str | None = None):
        """Disconnects the Lavalink Node."""
        try:
            node = wavelink.Pool.get_node("OiBot")
        except wavelink.InvalidNodeException:
            return await ctx.send("There is no node to disconnect")

        if not self.bot.voice_clients:
            await node.close(eject=True)
            return await ctx.send("Disconnected the node.")

        if message:
            end = f"This message will be sent if players are disconnected:\n{message}"
        else:
            end = "No message will be sent if players are disconnected."

        conf = await ctx.confirm(
            message=(
                f"Are you sure you want to disconnect the Node?\n"
                f"There are {len(self.bot.voice_clients)} connected players.\n{end}"
            ),
            remove_view_after=True,
        )

        if conf.result:
            self._players_to_restore = node.players  # type: ignore

            failed: int = 0

            end = f"\n\nDeveloper message:\n{message}" if message else ""

            for vc in self.bot.voice_clients:
                if isinstance(vc, Player):
                    try:
                        await vc.ctx.send(
                            "The music server is going to be disconnected.\n"
                            f"Your player will reconnect when the music server reconnects.{end}"
                        )
                    except discord.HTTPException:
                        failed += 1
                await vc.disconnect(force=True)

            await node.close(eject=True)
            content = "Disconnected the node and notified all players."
            if failed:
                content = f"Disconnected the node. Failed to notify {failed} of {len(self._players_to_restore)} players."
            return await conf.message.edit(content=content)
        return await conf.message.edit(content="Okay, the node will not be disconnected.")

    @Feature.Command(parent="jsk_music", name="connect")
    async def jsk_music_connect(self, ctx: Context):
        """Connects the Lavalink node."""
        try:
            node = wavelink.Pool.get_node("OiBot")
            if node:
                return await ctx.send("Node is already connected.")
        except wavelink.InvalidNodeException:
            pass
        msg = await ctx.send("Starting nodes...")
        await self.bot.start_wavelink_nodes()
        try:
            wavelink.Pool.get_node("OiBot")
        except wavelink.InvalidNodeException:
            return await msg.edit(content="Couldn't start node.")
        await msg.edit(content="Started Node.")

        if self._players_to_restore:
            cog: Music | None = self.bot.get_cog("Music")  # type: ignore
            if not cog:
                return await ctx.send("Couldn't restore players, Music cog is not loaded.")

            to_restore: list[asyncio.Task] = [
                self.bot.loop.create_task(cog._reconnect(vc)) for vc in self._players_to_restore.values()
            ]

            gather = await asyncio.gather(*to_restore)
            failed = len([result for result in gather if result is False])
            if failed:
                return await ctx.send(f"{failed} of {len(gather)} players failed to reconnect.")
            return await ctx.send("Restored all players.")
        return None

    @Feature.Command(parent="jsk_music", name="refresh")
    async def jsk_music_refresh(self, ctx: Context, *, flags: ConfigFlags):
        """Refresh the API tokens used by Lavalink."""

        node = wavelink.Pool.get_node("OiBot")
        if flags.po_token or flags.visitor_data or flags.refresh_token:
            yt_data = {}
            yt_changed = []
            if flags.po_token:
                yt_data["poToken"] = flags.po_token
                yt_changed.append("`po_token`")
            if flags.visitor_data:
                yt_data["visitorData"] = flags.visitor_data
                yt_changed.append("`visitor_data`")
            if flags.refresh_token:
                yt_data["refreshToken"] = flags.refresh_token
                yt_changed.append("`refresh_token`")
            try:
                await node.send("POST", path="youtube", data=yt_data)
                await ctx.send(f"Set YouTube data: {', '.join(yt_changed)}")
            except (wavelink.LavalinkException, wavelink.NodeException) as exc:
                await ctx.send(f"Could not set YouTube data: {exc}")

        data = {}
        changed = []
        for name, value in flags:
            if not value:
                continue
            try:
                changed.append(f"`{name}`")
                if config_mapping_sources[name] not in data:
                    data[config_mapping_sources[name]] = {}
                data[config_mapping_sources[name]][config_mapping_names[name]] = value
            except KeyError:
                # KeyError happens when po_token, visitor_data or refresh_token are set.
                # These were already set so we can just ignore it.
                continue

        if not changed:
            await ctx.send("Nothing was set.")
            return
        try:
            await node.send("PATCH", path="v4/lavasrc/config", data=data)
            await ctx.send(f"The following was set:\n{', '.join(changed)}.")
        except (wavelink.LavalinkException, wavelink.NodeException) as exc:
            await ctx.send(f"Could not set\n{', '.join(changed)}: {exc}")

    @Feature.Command(parent="jsk_music", name="source")
    async def jsk_music_source(self, ctx: Context, *, source: SEARCH_TYPES):
        """Sets the default source for the play command."""
        cog: Music | None = self.bot.get_cog("Music")  # type: ignore
        if not cog:
            return await ctx.send("Music cog isn't loaded.")
        cog.default_source = source
        return await ctx.send(f"Set the default source to {source}")


async def setup(bot: OiBot):
    await bot.add_cog(Owner(bot=bot))  # type: ignore
