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

import datetime
import inspect
import pathlib
from enum import Enum
from typing import Annotated, ClassVar, TYPE_CHECKING

import discord
import humanize
import psutil
import pytz
from discord import app_commands
from discord.ext import commands, menus
from discord.utils import _human_join as human_join
from jishaku.math import natural_size

import core
from utils import Paginator
from utils.types import Record

if TYPE_CHECKING:
    from core import Context, OiBot
    from utils import WeatherDict


NORMAL_PERMISSONS = discord.Permissions(1644942454270)
SOURCE_URL = "https://github.com/avizum/oi"


class CommandTypesConverter(int, Enum):
    all = 0
    slash = 1
    prefix = 2

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> int:
        try:
            return cls[argument].value
        except KeyError as exc:
            fmt = human_join([f'"{item.name}"' for item in cls])
            raise commands.BadArgument(f'Could not convert "{argument}" to {fmt}') from exc


CommandTypes = Annotated[int, CommandTypesConverter]


class UsagePageSource(menus.ListPageSource):
    def __init__(self, embed: discord.Embed, total: int, entries: list[str]) -> None:
        self.total = total
        self.embed = embed
        super().__init__(entries, per_page=15)

    async def format_page(self, menu: menus.Menu, entries: list[str]) -> discord.Embed:
        self.embed.remove_field(0)
        ent = "\n".join(entries)
        items = f"```\n{ent}```"
        self.embed.add_field(name=f"Commands ran: {self.total:,}", value=items)
        return self.embed


class UsesRecord(Record):
    command_name: str
    uses: int


class UserUsesRecord(Record):
    user_id: int
    uses: int


class TotalUsesRecord(Record):
    uses: int
    since: datetime.datetime


class Query:
    MAPPING: ClassVar[dict[int, str]] = {0: "", 1: "Slash ", 2: "Prefix "}

    TOTAL_USES = """
        SELECT CASE
            WHEN $1 = 0 THEN COUNT(*)
            WHEN $1 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $1 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses", MIN(used) as "since"
        FROM command_usage
    """

    TOP_USES = """
        SELECT command_name,
        CASE
            WHEN $1 = 0 THEN COUNT(*)
            WHEN $1 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $1 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        GROUP BY command_name
        ORDER BY uses DESC
        LIMIT 5
    """

    TOP_USES_TODAY = """
        SELECT command_name,
        CASE
            WHEN $1 = 0 THEN COUNT(*)
            WHEN $1 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $1 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
        GROUP BY command_name
        ORDER BY uses DESC
        LIMIT 5
    """

    GUILD_USES = """
        SELECT CASE
            WHEN $2 = 0 THEN COUNT(*)
            WHEN $2 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $2 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses", MIN(used) as "since"
        FROM command_usage
        WHERE guild_id = $1
    """

    GUILD_TOP_USES = """
        SELECT command_name,
        CASE
            WHEN $2 = 0 THEN COUNT(*)
            WHEN $2 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $2 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE guild_id = $1
        GROUP BY command_name
        ORDER BY uses DESC
        LIMIT 5
    """

    GUILD_TOP_USES_TODAY = """
        SELECT command_name,
        CASE
            WHEN $2 = 0 THEN COUNT(*)
            WHEN $2 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $2 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE guild_id = $1 AND used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
        GROUP BY command_name
        ORDER BY uses DESC
        LIMIT 5
    """

    GUILD_TOP_USERS = """
        SELECT user_id,
        CASE
            WHEN $2 = 0 THEN COUNT(*)
            WHEN $2 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $2 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE guild_id = $1
        GROUP BY user_id
        ORDER BY uses DESC
        LIMIT 5
    """

    GUILD_TOP_USERS_TODAY = """
        SELECT user_id,
        CASE
            WHEN $2 = 0 THEN COUNT(*)
            WHEN $2 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $2 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE guild_id = $1 AND used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
        GROUP BY user_id
        ORDER BY uses DESC
        LIMIT 5
    """

    MEMBER_USES = """
        SELECT CASE
            WHEN $3 = 0 THEN COUNT(*)
            WHEN $3 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $3 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses", MIN(used) as "since"
        FROM command_usage
        WHERE guild_id = $1 AND user_id = $2
    """

    MEMBER_TOP_USES = """
        SELECT command_name,
        CASE
            WHEN $3 = 0 THEN COUNT(*)
            WHEN $3 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $3 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE guild_id = $1 AND user_id = $2
        GROUP BY command_name
        ORDER BY uses DESC
        LIMIT 5
    """

    MEMBER_TOP_USES_TODAY = """
        SELECT command_name,
        CASE
            WHEN $3 = 0 THEN COUNT(*)
            WHEN $3 = 1 THEN COUNT(CASE WHEN app_command THEN 1 END)
            WHEN $3 = 2 THEN COUNT(CASE WHEN NOT app_command THEN 1 END)
        END AS "uses"
        FROM command_usage
        WHERE guild_id = $1 AND user_id = $2 AND used > (CURRENT_TIMESTAMP - INTERVAL '1 day')
        GROUP BY command_name
        ORDER BY uses DESC
        LIMIT 5
    """


class Utility(core.Cog):
    """Utility related commands."""

    def __init__(self, bot: OiBot) -> None:
        super().__init__(bot)
        self.report_webhook: discord.Webhook = discord.Webhook.from_url(bot.config["REPORT_WEBHOOK"], session=bot.session)

    @property
    def display_emoji(self) -> str:
        return "\U0001f6e0\U0000fe0f"

    @core.command()
    async def ping(self, ctx: core.Context):
        """Check the bot's latencies."""
        description = f"Bot Latency: `{(self.bot.latency * 1000):.2f}ms`"
        embed = discord.Embed(
            title="Pong!",
            description=description,
            color=0x00FFB3,
        )
        shard = self.bot.get_shard(ctx.guild.shard_id)
        if shard is not None:
            description += f"\nShard {shard.id} Latency: `{(shard.latency * 1000):.2f}ms`"
            embed.description = description
        await ctx.send(embed=embed)

    @core.command(no_tips=True)
    async def vote(self, ctx: Context):
        """Vote for Oi!"""
        embed = discord.Embed(
            title="Vote for Oi", description="Your support for Oi is greatly appreciated. Thank you!", color=0x00FFB3
        )
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Top.gg", emoji="<:topgg:1294459854894665768>", url="https://top.gg/bot/867713143366746142/vote"
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Discord Bot List",
                emoji="<:dbl:1294459668231356416>",
                url="https://discordbotlist.com/bots/oi/upvote",
            )
        )
        if ctx.author in self.bot.votes:
            embed.description = "You already voted, thank you for voting for Oi!"
        await ctx.send(embed=embed, view=view)

    @core.group()
    async def oi(self, ctx: Context):
        """Oi's informational commands."""
        return await ctx.send_help(ctx.command)

    @oi.command()
    async def invite(self, ctx: Context):
        """Get Oi's invite link."""
        await ctx.send(self.bot.invite_url)

    @oi.command(no_tips=True)
    async def support(self, ctx: Context):
        """Get Oi's support server invite link."""
        await ctx.send(self.bot.support_server)

    @oi.command()
    async def information(self, ctx: Context):
        """Get information about Oi."""
        embed = discord.Embed(title="Oi Information", color=0x00FFB3)

        embed.add_field(
            name="<:developer:1294459993889706097> Developers",
            value=(
                "[rolex6956](https://discord.com/users/531179463673774080)\n"
                "[avizum](https://discord.com/users/750135653638865017)\n"
            ),
            inline=False,
        )

        delta_uptime = datetime.datetime.now(tz=datetime.timezone.utc) - self.bot.launched_at
        uptime = humanize.precisedelta(delta_uptime, format="%.2g")

        embed.add_field(
            name="\U00002139\U0000fe0f Bot Status",
            value=(
                f"Servers: {len(self.bot.guilds):,}\n"
                f"Users: {sum(int(g.member_count) for g in self.bot.guilds):,}\n"  # type: ignore
                f"Shards: {self.bot.shard_count}\n"
                f"Uptime: {uptime}\n"
                f"Latency: {round(self.bot.latency * 1000)}ms"
            ),
            inline=False,
        )

        process = psutil.Process()
        with process.oneshot():
            mem = process.memory_full_info()
            used_mem = natural_size(mem.rss)
            vmem = natural_size(mem.vms)
            uvmem = natural_size(mem.uss)
            pid = process.pid
            threads = process.num_threads()
            cpu = process.cpu_percent()

        embed.add_field(
            name="\U00002699\U0000fe0f Process Information",
            value=(
                f"Process ID: {pid}\n"
                f"CPU Used: {cpu}%\n"
                f"Physical Memory Used: {used_mem}\n"
                f"Virtual Memory Used: {vmem}\n"
                f"Virtual Memory Used (Process): {uvmem}\n"
                f"Thread Count: {threads}"
            ),
            inline=False,
        )

        embed.set_footer(
            text=f"Made in Python using discord.py {discord.__version__}", icon_url=self.bot.user.display_avatar.url
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await ctx.send(embed=embed)

    @oi.command()
    @core.describe(command="The command to show the source of")
    async def source(self, ctx: Context, command: str | None = None):
        """View the source of Oi.

        Typing a command will send the source of the command.
        """

        view = discord.ui.View()
        if not command:
            view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label="Source", url=SOURCE_URL))
            return await ctx.send("Here is the source.", view=view)

        cmd = self.bot.help_command if command == "help" else self.bot.get_command(command)
        if not cmd:
            return await ctx.send("Could not find command.", view=view)

        if isinstance(cmd, commands.HelpCommand):
            lines, beginning = inspect.getsourcelines(type(command))
            src = command.__module__
        else:
            lines, beginning = inspect.getsourcelines(cmd.callback.__code__)
            src = cmd.callback.__module__

        path = f"{src.replace('.', '/')}.py"

        end = beginning + len(lines) - 1
        link = f"{SOURCE_URL}/blob/main/{path}#L{beginning}-L{end}"

        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=f"Source for {command}", url=link))
        return await ctx.send("Here is the source.", view=view)

    @source.autocomplete("command")
    async def source_command_autocomplete(self, itn: discord.Interaction, current: str) -> list[app_commands.Choice]:
        return [
            app_commands.Choice(name=cmd.qualified_name, value=cmd.qualified_name)
            for cmd in self.bot.walk_commands()
            if current in cmd.qualified_name
        ][:25]

    @oi.command()
    async def linecount(self, ctx: Context):
        """Check how many lines of code the bot has."""
        path = pathlib.Path("./")
        comments = coros = funcs = classes = lines = imports = files = char = 0
        for item in path.rglob("*.py"):
            if str(item).startswith(".env"):
                continue
            files += 1
            with item.open() as of:
                for source_line in of.readlines():
                    line = source_line.strip()
                    if line.startswith("class"):
                        classes += 1
                    if line.startswith("def"):
                        funcs += 1
                    if line.startswith("async def"):
                        coros += 1
                    if "import" in line:
                        imports += 1
                    if "#" in line:
                        comments += 1
                    lines += 1
                    char += len(line)
        embed = discord.Embed(
            title="Line Count",
            description=(
                "```py\n"
                f"Files: {files:,}\n"
                f"Imports: {imports:,}\n"
                f"Characters: {char:,}\n"
                f"Lines: {lines:,}\n"
                f"Classes: {classes:,}\n"
                f"Functions: {funcs:,}\n"
                f"Coroutines: {coros:,}\n"
                f"Comments: {comments:,}"
                "```"
            ),
        )
        await ctx.send(embed=embed)

    @oi.command()
    async def uptime(self, ctx: Context):
        """Check Oi's uptime."""
        delta_uptime = datetime.datetime.now(tz=datetime.timezone.utc) - self.bot.launched_at
        await ctx.send(f"Oi has been up for {humanize.precisedelta(delta_uptime, format='%.2g')}")

    @oi.command()
    async def shards(self, ctx: Context):
        """Shows informations about the shards."""
        shard_list = []
        for shard_id, shard in self.bot.shards.items():
            guilds = [g for g in self.bot.guilds if g.shard_id == shard_id]
            user_count = sum(int(guild.member_count) for guild in guilds)  # type: ignore
            latency = "N/A" if shard.latency == float("inf") else round(shard.latency * 1000)
            status = "Offline" if shard.is_closed() else "Online"
            shard_list.append((shard_id, len(guilds), user_count, latency, status))

        embed = discord.Embed(title="Shard Information", color=0x00FFB3)

        # fmt: off
        for shard_id, guilds, users, latency, status in shard_list:
            embed.add_field(
                name=f"Shard {shard_id}",
                value=(
                    f"Servers: {guilds:,}\n"
                    f"Users: {users:,}\n"
                    f"Latency: {latency}ms\n"
                    f"Status: {status}"
                ),
                inline=True,
            )

        await ctx.send(embed=embed)
        # fmt: on

    def get_user(self, user_id: int) -> str:
        try:
            user = self.bot.cached_users[user_id][0]
        except KeyError:
            return "Not Found"
        else:
            return user.name

    def format_usage(self, record: list[UsesRecord | UserUsesRecord]) -> str:
        fmt = []
        if not record:
            return "No command usage."
        if isinstance(record[0], UserUsesRecord):
            for count, row in enumerate(record, start=1):
                fmt.append(f"{count}. {self.get_user(row.user_id)}: {row.uses:,} command uses")
        else:
            for count, row in enumerate(record, start=1):
                fmt.append(f"{count}. {row.command_name}: {row.uses:,} uses")
        return "\n".join(fmt)

    def midnight_timestamp(self) -> str:
        midnight = (datetime.datetime.now() + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return discord.utils.format_dt(midnight, "R")

    @oi.group(fallback="server")
    @core.describe(command_type="What type of command usage to show.")
    @app_commands.rename(command_type="type")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def usage(self, ctx: Context, command_type: CommandTypes = 0):
        """Shows command usage for this server."""
        cmd_type = Query.MAPPING[command_type]
        pool = self.bot.pool

        async with ctx.typing():
            args = (ctx.guild.id, command_type)
            total_uses: TotalUsesRecord = await pool.fetchrow(Query.GUILD_USES, *args, record_class=TotalUsesRecord)
            if not total_uses.uses:
                return await ctx.send(f"No {cmd_type}command usage logged for {ctx.guild} yet.")

            top_uses: list[UsesRecord] = await pool.fetch(Query.GUILD_TOP_USES, *args, record_class=UsesRecord)
            top_uses_today: list[UsesRecord] = await pool.fetch(Query.GUILD_TOP_USES_TODAY, *args, record_class=UsesRecord)
            top_users: list[UserUsesRecord] = await pool.fetch(Query.GUILD_TOP_USERS, *args, record_class=UserUsesRecord)
            await self.bot.fetch_users(*[row.user_id for row in top_users])

            top_users_today: list[UserUsesRecord] = await pool.fetch(
                Query.GUILD_TOP_USERS_TODAY, *args, record_class=UserUsesRecord
            )
            await self.bot.fetch_users(*[row.user_id for row in top_users_today])

        embed = discord.Embed(
            title=f"{cmd_type}Command Usage for {ctx.guild.name}",
            description=(
                f"This server has {total_uses.uses:,} {cmd_type}command uses.\n"
                f"Top {cmd_type}Commands reset in: {self.midnight_timestamp()}"
            ),
            timestamp=total_uses.since.replace(tzinfo=datetime.timezone.utc),
        )
        embed.add_field(name=f"Top {cmd_type}Commands", value=self.format_usage(top_uses))
        embed.add_field(name=f"Top {cmd_type}Commands Today", value=self.format_usage(top_uses_today))
        embed.add_field(name="\u200b", value="\u200b")
        embed.add_field(name=f"Top {cmd_type}Command Users", value=self.format_usage(top_users))
        embed.add_field(name=f"Top {cmd_type}Command Users Today", value=self.format_usage(top_users_today))
        embed.add_field(name="\u200b", value="\u200b")
        embed.set_footer(text="Tracking since", icon_url=self.bot.user.display_avatar.url)

        return await ctx.send(embed=embed)

    @usage.command(name="member")
    @core.describe(member="The member's command usage you want to see.", command_type="What type of command usage to show.")
    @app_commands.rename(command_type="type")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def usage_member(self, ctx: Context, member: discord.Member = commands.Author, command_type: CommandTypes = 0):
        """Shows command usage for a member in this server"""
        cmd_type = Query.MAPPING[command_type]
        pool = self.bot.pool

        async with ctx.typing():
            args = (ctx.guild.id, member.id, command_type)
            total_uses: TotalUsesRecord = await pool.fetchrow(Query.MEMBER_USES, *args, record_class=TotalUsesRecord)
            if not total_uses.uses:
                noun = member if member != ctx.author else "you"
                return await ctx.send(f"No {cmd_type}command usage logged for {noun} yet.")
            top_uses: list[UsesRecord] = await pool.fetch(Query.MEMBER_TOP_USES, *args, record_class=UsesRecord)
            top_uses_today: list[UsesRecord] = await pool.fetch(Query.MEMBER_TOP_USES_TODAY, *args, record_class=UsesRecord)

        start = f"{member} has" if member != ctx.author else "You have"
        embed = discord.Embed(
            title=f"{cmd_type}Command Usage for {member}",
            description=(
                f"{start} used {total_uses.uses:,} {cmd_type}commands.\n"
                f"Top {cmd_type}Commands reset in: {self.midnight_timestamp()}"
            ),
            timestamp=total_uses.since.replace(tzinfo=datetime.timezone.utc),
        )

        start = f"{member}'s" if member != ctx.author else "Your"
        embed.add_field(name=f"{start} Top {cmd_type}Commands", value=self.format_usage(top_uses))
        embed.add_field(name=f"{start} Top {cmd_type}Commands Today", value=self.format_usage(top_uses_today))
        embed.set_footer(text="Tracking since", icon_url=self.bot.user.display_avatar.url)
        return await ctx.send(embed=embed)

    @usage.command(name="global")
    @core.describe(command_type="What type of command usage to show.")
    @app_commands.rename(command_type="type")
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def usage_global(self, ctx: Context, command_type: CommandTypes = 0):
        """Shows global command usage."""
        cmd_type = Query.MAPPING[command_type]
        pool = self.bot.pool

        async with ctx.typing():
            total_uses: TotalUsesRecord = await pool.fetchrow(Query.TOTAL_USES, command_type, record_class=TotalUsesRecord)
            if not total_uses.uses:
                # This should only happen if there are no entries in the database, which would be very bad.
                return await ctx.send("No command usage logged for some reason.")

            top_uses: list[UsesRecord] = await pool.fetch(Query.TOP_USES, command_type, record_class=UsesRecord)
            top_uses_today: list[UsesRecord] = await pool.fetch(Query.TOP_USES_TODAY, command_type, record_class=UsesRecord)

        embed = discord.Embed(
            title="Global Command Usage",
            description=(
                f"{total_uses.uses:,} {cmd_type}commands used.\nTop {cmd_type}Commands reset in: {self.midnight_timestamp()}"
            ),
            timestamp=total_uses.since.replace(tzinfo=datetime.timezone.utc),
        )

        embed.add_field(name=f"Top {cmd_type}Commands", value=self.format_usage(top_uses))
        embed.add_field(name=f"Top {cmd_type}Commands Today", value=self.format_usage(top_uses_today))
        embed.set_footer(text="Tracking since", icon_url=self.bot.user.display_avatar.url)
        return await ctx.send(embed=embed)

    @usage.command(name="session")
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def usage_session(self, ctx: Context):
        """Shows all command usage stats from last reboot."""
        usage = self.bot.command_usage
        most_use = dict(sorted(usage.items(), key=lambda item: item[1], reverse=True))

        uh = humanize.precisedelta(datetime.datetime.now(tz=datetime.timezone.utc) - self.bot.launched_at)
        em = discord.Embed(
            title="Oi Usage",
            description=f"Oi has been up for `{uh}`\nUse {self.usage_global.mention} to see all time usage.",
            color=0x00FFB3,
        )
        most = [f"{k}: {v:,}" for k, v in most_use.items()]
        total = sum(usage.values())
        source = UsagePageSource(em, total, most)
        paginator = Paginator(source=source, ctx=ctx, remove_view_after=True)
        await paginator.start()

    @oi.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    @core.describe(message="The message to send to the support server.")
    async def report(self, ctx: Context, *, message: str):
        """Send a report to the support server."""
        if len(message) > 1000:
            return await ctx.send("Your message is too long!")
        await self.report_webhook.send(content=f"**{ctx.author}**:\n{message}\n")
        return await ctx.send("Report sent!")

    @oi.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def diagnose(self, ctx: Context):
        """Check which commands can't be ran by the bot."""
        cant_run = []
        bot_commands: set[core.Command] = {
            c for c in self.bot.walk_commands() if c.parent != self.bot.get_command("jishaku")
        }  # type: ignore

        for command in bot_commands:
            bot_perm = getattr(command, "bot_permissions", None)
            cmd_bot_perms = bot_perm or getattr(command, "bot_guild_permissions", None)
            bot_perms = ctx.bot_permissions if bot_perm else ctx.bot_guild_permissions
            if cmd_bot_perms:
                missing = [perm for perm in cmd_bot_perms if not getattr(bot_perms, perm)]
                if missing:
                    fmtd = ", ".join(missing).replace("_", " ").replace("guild", "server").title()
                    cant_run.append(f"`{command.qualified_name}` (Missing: {fmtd})")

        embed = discord.Embed(title="Diagnosis", description="I can run all commands. Nice!", color=0x00FFB3)
        if cant_run:
            embed.description = (
                f"I can run {len(bot_commands) - len(cant_run)} out of {len(bot_commands)} commands.\n"
                f"Please [reauthorize]({self.bot.invite_url}) me to fix this."
            )
            nl = "\n"
            embed.add_field(name="Can't Run", value=f"{nl.join(cant_run)}", inline=False)
        await ctx.send(embed=embed)

    @core.group(fallback="info", aliases=["userinfo"])
    @core.describe(user="The user to get informations about.")
    async def user(self, ctx: Context, user: discord.Member | discord.User = commands.Author):
        """
        Shows some information about a user.
        """
        member = user or ctx.author
        if isinstance(member, discord.Member):
            embed = discord.Embed(title=member, color=member.color)
            embed.add_field(name="ID", value=member.id, inline=False)
            if member.nick:
                embed.add_field(name="Nickname", value=member.nick, inline=False)
            if member.joined_at:
                joined = f"{discord.utils.format_dt(member.joined_at)} ({discord.utils.format_dt(member.joined_at, 'R')})"
                embed.add_field(name="Joined", value=joined, inline=False)
            created = f"{discord.utils.format_dt(member.created_at)} ({discord.utils.format_dt(member.created_at, 'R')})"
            embed.add_field(name="Created", value=created, inline=False)
            roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
            embed.add_field(name="Roles", value=", ".join(roles), inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            await ctx.send(embed=embed)
        elif isinstance(member, discord.User):
            embed = discord.Embed(title=member, color=0x00FFB3)
            embed.add_field(name="ID", value=member.id, inline=False)
            embed.add_field(name="Created", value=discord.utils.format_dt(member.created_at), inline=False)
            embed.set_thumbnail(url=member.display_avatar.url)
            await ctx.send(embed=embed)

    @user.command()
    @core.describe(user="The user to get the avatar of.")
    async def avatar(self, ctx: Context, user: discord.Member | discord.User = commands.Author):
        """
        Shows a user's avatar.
        """
        member = user or ctx.author

        embed = discord.Embed(color=member.color)
        if member.avatar:
            embed.set_image(url=member.avatar.url)
            urls = (
                f"[`png`]({member.display_avatar.replace(format='png')}) | "
                f"[`jpeg`]({member.display_avatar.replace(format='jpeg')}) | "
                f"[`webp`]({member.display_avatar.replace(format='webp')})"
            )
            if member.avatar.is_animated():
                urls += f" | [`gif`]({member.display_avatar.replace(format='gif')})"
            embed.description = urls
        else:
            embed.set_image(url=member.default_avatar.url)

        await ctx.send(embed=embed)

    @user.command()
    @core.describe(user="The user to get the banner of.")
    async def banner(self, ctx: Context, user: discord.Member | discord.User = commands.Author):
        """
        Shows a user's banner.
        """
        to_fetch = user or ctx.author
        member = await self.bot.fetch_user(to_fetch.id)

        if member.banner:
            embed = discord.Embed(color=member.color)
            embed.set_image(url=member.banner.url)
            urls = (
                f"[`png`]({member.banner.replace(format='png')}) | "
                f"[`jpeg`]({member.banner.replace(format='jpeg')}) | "
                f"[`webp`]({member.banner.replace(format='webp')})"
            )
            if member.banner.is_animated():
                urls += f" | [`gif`]({member.banner.replace(format='gif')})"
            embed.description = urls
            await ctx.send(embed=embed)
        else:
            await ctx.send("This user doesn't have a banner.")

    @core.command()
    @core.describe(query="The item to search for.")
    async def pypi(self, ctx: Context, query: str):
        """
        Searches PyPi for packages.
        """

        url = f"https://pypi.org/pypi/{query}/json"
        response = await self.bot.session.get(url)
        if response.status != 200:
            return await ctx.send("No results found.")

        data = await response.json()

        embed = discord.Embed(
            title=f"{data['info']['name']} {data['info']['version']}", description=data["info"]["summary"], color=0x0273B7
        )

        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/790354100654964776/1059307925996322887/logo.png")

        author = f"{data['info']['author']}"
        if data["info"]["author_email"]:
            author += f" ({data['info']['author_email']})"

        embed.add_field(name="Author", value=author, inline=False)

        embed.add_field(
            name="Package Information",
            value=(
                f"Version: {data['info']['version']}\n"
                f"License: {data['info']['license']}\n"
                f"Requires Python: {data['info']['requires_python']}\n"
                f"Package URL: {data['info']['package_url']}\n"
                f"Home page: {data['info']['home_page']}\n"
                f"Documentation: {data['info']['docs_url']}\n"
            ),
            inline=False,
        )

        return await ctx.send(embed=embed)

    @core.command()
    @core.describe(location="Where to get the weather for.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def weather(self, ctx: Context, location: str):
        """
        Get the weather.
        """
        resp = await self.bot.session.get(
            f"https://api.weatherapi.com/v1/current.json?key={self.bot.config['WEATHER_API']}&q={location}"
        )
        data: WeatherDict = await resp.json()

        if data.get("error"):
            return await ctx.send("An error occurred while fetching the weather.")

        locale = data["location"]
        current = data["current"]
        conditions = current["condition"]

        embed = discord.Embed(title="Weather")

        dt = datetime.datetime.now(pytz.timezone(locale["tz_id"])).strftime("%A, %B %d, %I:%M %p")
        embed.add_field(name="Location", value=f"{locale['name']}, {locale['region']}\nLocal Time: {dt}", inline=False)

        metric = False if not ctx.interaction else ctx.interaction.locale != discord.Locale.american_english
        temperature = f"{current['temp_c']} °C" if metric else f"{current['temp_f']} °F"
        feels_like = f"{current['feelslike_c']} °C" if metric else f"{current['feelslike_f']} °F"
        wind_speed = f"{current['wind_kph']} kph" if metric else f"{current['wind_mph']} mph"
        gusts = f"{current['gust_kph']} kph" if metric else f"{current['gust_mph']} mph"
        visibility = f"{current['vis_km']} km" if metric else f"{current['vis_miles']} miles"
        precipitation = f"{current['precip_mm']} mm" if metric else f"{current['precip_in']} in"
        pressure = f"{current['pressure_mb']} mb" if metric else f"{current['pressure_in']} inHg"

        embed.add_field(
            name="Forecast",
            value=(
                f"Conditions: {conditions['text']}\n"
                f"Temperature: {temperature}\n"
                f"Feels Like: {feels_like}\n"
                f"Wind: {wind_speed} {current['wind_dir']}\n"
                f"Gusts: Up to {gusts}\n"
                f"Precipitation: {precipitation}\n"
                f"Humidity: {current['humidity']}%\n"
                f"Cloud Cover: {current['cloud']}%\n"
                f"Visibility: {visibility}\n"
                f"UV Index: {current['uv']}\n"
                f"Pressure: {pressure}\n"
            ),
            inline=False,
        )

        embed.set_thumbnail(url=f"https:{conditions['icon']}")
        return await ctx.send(embed=embed)


async def setup(bot: OiBot):
    await bot.add_cog(Utility(bot))
