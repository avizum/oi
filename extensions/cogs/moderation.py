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

import datetime
import re
from typing import Annotated, TYPE_CHECKING

import discord
import humanize
from discord import app_commands
from discord.ext import commands

import core

if TYPE_CHECKING:
    from discord import Interaction, Member

    from core import Context, OiBot


class TargetConverter(app_commands.Transformer):
    @property
    def type(self):
        return discord.AppCommandOptionType.user

    async def base(self, ctx: Context, target: Member) -> Member:
        mod = ctx.author
        action = ctx.command.name
        guild = ctx.guild
        bot = ctx.me

        if mod.id == guild.owner_id:
            return target
        if target == guild.owner:
            raise commands.BadArgument(f"I can not {action} the server owner.")
        if target == bot:
            raise commands.BadArgument(f"I can not {action} myself.")
        elif target == mod:
            raise commands.BadArgument(f"Can not {action} yourself.")
        elif bot.top_role <= target.top_role:
            raise commands.BadArgument(f"I can not {action} someone with a higher or equal role to me.")
        elif mod.top_role <= target.top_role:
            raise commands.BadArgument(f"You can not {action} someone with a higher or equal role to you.")
        return target

    async def convert(self, ctx: Context, argument: str) -> Member:
        member = await commands.MemberConverter().convert(ctx, argument)
        return await self.base(ctx, member)

    async def transform(self, itn: Interaction, argument: Member) -> Member:
        ctx = itn._baton
        return await self.base(ctx, argument)


class ReasonConverter(app_commands.Transformer):
    async def base(self, ctx: Context, argument: str) -> str:
        reason = f"{ctx.author}: {argument}"

        if len(reason) > 120:
            raise commands.BadArgument(f"Reason is too long ({len(reason)}/120)")
        return reason

    async def convert(self, ctx: Context, argument: str) -> str:
        return await self.base(ctx, argument)

    async def transform(self, itn: Interaction, argument: str) -> str:
        ctx = itn._baton
        return await self.base(ctx, argument)


class FindBanEntry(app_commands.Transformer):
    async def base(self, ctx: Context, argument: str) -> discord.User:
        try:
            user = await commands.UserConverter().convert(ctx, argument)
            try:
                await ctx.guild.fetch_ban(user)
            except discord.NotFound as e:
                raise commands.BadArgument("That user isn't banned.") from e
            return user
        except commands.UserNotFound:
            bans = [entry async for entry in ctx.guild.bans()]
            for ban in bans:
                if str(ban[1]).startswith(argument):
                    return ban[1]

        raise commands.BadArgument("That user isn't banned")

    async def convert(self, ctx: Context, argument: str) -> discord.User:
        return await self.base(ctx, argument)

    async def transform(self, itn: Interaction, argument: str) -> discord.User:
        ctx = itn._baton
        return await self.base(ctx, argument)


class RoleTarget(app_commands.Transformer):
    @property
    def type(self):
        return discord.AppCommandOptionType.role

    async def base(self, ctx: Context, role: discord.Role) -> discord.Role:
        if role > ctx.me.top_role:
            raise commands.BadArgument("That role is higher than my highest role.")
        elif role > ctx.author.top_role:
            raise commands.BadArgument("That role is higher than your highest role.")
        elif role == ctx.guild.default_role:
            raise commands.BadArgument("Can not modify @\u200beverone role.")
        elif role.managed:
            raise commands.BadArgument("Can not modify a managed role.")

        return role

    async def convert(self, ctx: Context, argument: str) -> discord.Role:
        role = await commands.RoleConverter().convert(ctx, argument)
        return await self.base(ctx, role)

    async def transform(self, itn: Interaction, argument: discord.Role) -> discord.Role:
        ctx = itn._baton
        return await self.base(ctx, argument)


time_regex = re.compile(r"(?:(\d{1,5})\s?(h|s|m|d|w|y))+?")
time_dict = {
    "h": 3600,
    "hours": 3600,
    "hour": 3600,
    "s": 1,
    "sec": 1,
    "secs": 1,
    "seconds": 1,
    "m": 60,
    "mins": 60,
    "minutes": 60,
    "min": 60,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
    "y": 31557600,
    "year": 31557600,
    "years": 31557600,
}


class TimeConverter(app_commands.Transformer):
    @property
    def type(self):
        return discord.AppCommandOptionType.string

    async def base(self, ctx: Context, argument) -> int:
        args = argument.lower()
        matches = re.findall(time_regex, args)
        time = 0
        for key, value in matches:
            try:
                time += time_dict[value] * float(key)
            except KeyError as e:
                raise commands.BadArgument(f"{value} is an invalid unit of time!") from e
            except ValueError as e:
                raise commands.BadArgument(f"{key} is not a number!") from e
        if time < 0:
            raise commands.BadArgument("Time can not be under 1 second")
        return int(time)

    async def convert(self, ctx: Context, argument: str) -> int:
        return await self.base(ctx, argument)

    async def transform(self, itn: Interaction, argument: str) -> int:
        ctx = itn._baton
        return await self.base(ctx, argument)


Target = Annotated[discord.Member, TargetConverter]
Reason = Annotated[str, ReasonConverter]
BanEntry = Annotated[discord.User, FindBanEntry]
Time = Annotated[int, TimeConverter]
TargetRole = Annotated[discord.Role, RoleTarget]
DefaultReason = commands.parameter(
    converter=ReasonConverter, default=lambda ctx: f"Action done by {ctx.author}", displayed_default="<none>"
)


class Moderation(core.Cog):
    """
    Moderation related commands.
    """

    @property
    def display_emoji(self) -> str:
        return "<:modd:887743787722506380>"

    @staticmethod
    async def do_removal(ctx: Context, *args, **kwargs) -> list[discord.Message]:
        async with ctx.typing():
            messages = await ctx.channel.purge(*args, **kwargs)
        return messages

    @staticmethod
    async def show_results(ctx: Context, messages: list[discord.Message]) -> discord.Embed:
        results = {}
        for message in messages:
            if message.author not in results:
                results[message.author] = 1
            else:
                results[message.author] += 1

        return discord.Embed(
            title="Affected Messages", description="\n".join(f"{k}: {v} messages" for k, v in results.items())
        )

    @core.command()
    @core.has_permissions(kick_members=True)
    @core.bot_has_permissions(kick_members=True)
    @core.describe(target="The member to kick.", reason="The reason that will show up in the audit log.")
    async def kick(self, ctx: Context, target: Target, *, reason: Reason = DefaultReason):
        """
        Kick a member from the server.
        """
        await ctx.guild.kick(user=target, reason=reason)
        await ctx.send(f"Kicked {target}.", ephemeral=True)

    @core.command()
    @core.has_permissions(ban_members=True)
    @core.bot_has_permissions(ban_members=True)
    @core.describe(target="The member to ban.", reason="The reason that will show up in the audit log.")
    async def ban(self, ctx: Context, target: Target, *, reason: Reason = DefaultReason):
        """
        Ban a member from the server.
        """
        await ctx.guild.ban(user=target, reason=reason)
        await ctx.send(f"Banned {target}.", ephemeral=True)

    @core.command()
    @core.has_permissions(ban_members=True)
    @core.bot_has_permissions(ban_members=True)
    @core.describe(target="The user to unban.", reason="The reason that will show up in the audit log.")
    async def unban(self, ctx: Context, target: BanEntry, *, reason: Reason = DefaultReason):
        """
        Unban a member from the server.
        """
        await ctx.guild.unban(user=target, reason=reason)
        await ctx.send(f"Unbanned {target}.", ephemeral=True)

    @core.command()
    @core.has_permissions(kick_members=True)
    @core.bot_has_permissions(kick_members=True)
    @core.describe(target="The member to softban.", reason="The reason that will show up in the audit log.")
    async def softban(self, ctx: Context, target: Target, *, reason: Reason = DefaultReason):
        """
        Softban a member from the server.
        """
        await ctx.guild.ban(user=target, reason=reason)
        await ctx.guild.unban(user=target, reason=reason)
        await ctx.send(f"Softbanned {target}.", ephemeral=True)

    @core.command()
    @core.bot_has_permissions(manage_messages=True, read_message_history=True)
    @core.describe(amount="The amount of messages to delete.")
    async def cleanup(self, ctx: Context, amount: commands.Range[int, 1, 100] = 15):
        """
        Deletes messages sent by the bot in the channel.

        If user does not have sufficient permissions, a maximum of 10 messages can be deleted.
        """
        if not ctx.permissions.manage_messages and amount > 10:
            amount = 10
        msgs = await self.do_removal(ctx, limit=amount, before=ctx.message.created_at, check=lambda m: m.author == ctx.me)
        await ctx.send(embed=await self.show_results(ctx, msgs), ephemeral=True)

    @core.command()
    @core.has_permissions(manage_messages=True)
    @core.bot_has_permissions(manage_messages=True, read_message_history=True)
    @core.describe(amount="The amount of messages to delete.")
    async def purge(self, ctx: Context, amount: commands.Range[int, 1, 100]):
        """
        Bulk delete messages in the channel.
        """
        msgs = await self.do_removal(ctx, limit=amount, before=ctx.message.created_at)
        await ctx.send(embed=await self.show_results(ctx, msgs), ephemeral=True)

    @core.group()
    @core.has_permissions(manage_channels=True)
    @core.bot_has_permissions(manage_channels=True)
    async def channel(self, ctx: Context):
        """
        Manage channels.
        """
        await ctx.send_help(ctx.command)

    @channel.command(name="lock")
    @core.has_permissions(manage_channels=True)
    @core.bot_has_permissions(manage_channels=True)
    @core.describe(channel="The channel to lock.", reason="The reason that will show up in the audit log.")
    async def channel_lock(
        self, ctx: Context, channel: discord.TextChannel | discord.VoiceChannel, *, reason: Reason = DefaultReason
    ):
        """
        Lock a channel.

        This will deny the @everyone role from sending messages in the channel, creating threads,
        and sending messages in threads.
        If the channel is a voice channel, @everyone will also be denied from connecting to the channel.
        """
        await channel.set_permissions(
            ctx.guild.default_role,
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            connect=False,
            reason=reason,
        )
        await ctx.send(f"Locked {channel.mention}.", ephemeral=True)
        await channel.send("\U0001f512 This channel has been locked by a moderator.")

    @channel.command(name="unlock")
    @core.has_permissions(manage_channels=True)
    @core.bot_has_permissions(manage_channels=True)
    @core.describe(channel="The channel to unlock.", reason="The reason that will show up in the audit log.")
    async def channel_unlock(
        self, ctx: Context, channel: discord.TextChannel | discord.VoiceChannel, *, reason: Reason = DefaultReason
    ):
        """
        Unlock a channel.

        Reverses the effects of the lock command.
        """
        await channel.set_permissions(
            ctx.guild.default_role,
            send_messages=None,
            send_messages_in_threads=None,
            create_public_threads=None,
            create_private_threads=None,
            connect=None,
            reason=reason,
        )
        await ctx.send(f"Unlocked {channel.mention}.", ephemeral=True)
        await channel.send("\U0001f513 This channel has been unlocked by a moderator.")

    @channel.command(name="slowmode")
    @core.has_permissions(manage_channels=True)
    @core.bot_has_permissions(manage_channels=True)
    @core.describe(
        channel="The channel to slowmode.",
        delay="The new slowmode delay.",
        reason="The reason that will show up in the audit log.",
    )
    async def channel_slowmode(
        self,
        ctx: Context,
        channel: discord.TextChannel | discord.VoiceChannel,
        delay: Time = 0,
        reason: Reason = DefaultReason,
    ):
        """
        Change a channel's slowmode.
        """
        if delay > 21600:
            raise commands.BadArgument("Slowmode delay cannot be more than 6 hours.")

        to_edit = ctx.channel or channel
        if isinstance(to_edit, discord.Thread) and to_edit.parent:
            await to_edit.parent.edit(slowmode_delay=delay, reason=reason)
        else:
            await to_edit.edit(slowmode_delay=delay, reason=reason)  # type: ignore
        await ctx.send(f"Slowmode for {to_edit.mention} set to {humanize.precisedelta(delay)}", ephemeral=True)

    @core.command()
    @core.has_permissions(manage_nicknames=True)
    @core.bot_has_permissions(manage_nicknames=True)
    @core.describe(
        target="The member to change the nickname of.",
        nickname="The new nickname for the member.",
        reason="The reason that will show up in the audit log.",
    )
    async def nick(
        self, ctx: Context, target: Target, *, nickname: commands.Range[str, None, 32], reason: Reason = DefaultReason
    ):
        """
        Change a member's nickname.
        """
        await target.edit(nick=nickname, reason=reason)
        await ctx.send(f"Changed {target.mention}'s nickname.", ephemeral=True)

    @core.group()
    @core.has_permissions(manage_roles=True)
    @core.bot_has_permissions(manage_roles=True)
    async def role(self, ctx: Context):
        """
        Manage roles.
        """
        await ctx.send_help(ctx.command)

    @role.command(name="create")
    @core.has_permissions(manage_roles=True)
    @core.bot_has_permissions(manage_roles=True)
    @core.describe(
        name="The name of the role.",
        hoist="Whether the role should be hoisted to the top.",
        color="The color of the role.",
        reason="The reason that will show up in the audit log.",
    )
    async def role_create(
        self,
        ctx: Context,
        name: str,
        hoist: bool = False,
        color: discord.Color = discord.Color.default(),
        *,
        reason: Reason = DefaultReason,
    ):
        """
        Create a role.
        """
        await ctx.guild.create_role(name=name, hoist=hoist, color=color, reason=reason)
        await ctx.send(f"Created role {name}.", ephemeral=True)

    @role.command(name="delete")
    @core.has_permissions(manage_roles=True)
    @core.bot_has_permissions(manage_roles=True)
    @core.describe(
        role="The role to delete.",
        reason="The reason that will show up in the audit log.",
    )
    async def role_delete(self, ctx: Context, role: TargetRole, *, reason: Reason = DefaultReason):
        """
        Delete a role.
        """
        try:
            await role.delete(reason=reason)
        except discord.Forbidden as e:
            raise commands.BadArgument("I cannot delete this role.") from e
        await ctx.send(f"Deleted role {role.mention}.", ephemeral=True)

    @role.command(name="add")
    @core.has_permissions(manage_roles=True)
    @core.bot_has_permissions(manage_roles=True)
    @core.describe(
        target="The member to add the roles to.",
        roles="The roles (wrapped in quotes), to add to the member.",
        reason="The reason that will show up in the audit log.",
    )
    async def role_add(
        self, ctx: Context, target: Target, roles: commands.Greedy[discord.Role], *, reason: Reason = DefaultReason
    ):
        """
        Add a role to a member.
        """
        errors = []
        for role in roles:
            if role > ctx.me.top_role:
                errors.append(f"{role.mention}: This role is higher than my top role.")
                roles.remove(role)
            elif role == ctx.me.top_role:
                errors.append(f"{role.mention}: This role is equal to my top role.")
                roles.remove(role)
            elif role > ctx.author.top_role:
                errors.append(f"{role.mention}: This role is higher than your top role.")
                roles.remove(role)
            elif role == ctx.author.top_role:
                errors.append(f"{role.mention}: This role is equal to your top role.")
                roles.remove(role)
            elif role in target.roles:
                errors.append(f"{role.mention}: Member already has this role.")
                roles.remove(role)
            elif role.managed:
                errors.append(f"{role.mention}: Can not add managed roles.")
                roles.remove(role)

        await target.add_roles(*roles, reason=reason)
        added_roles = "\n".join(role.mention for role in roles)
        not_added_roles = "\n".join(errors)

        embed = discord.Embed(title=f"Edited {target} roles")
        if added_roles:
            embed.add_field(name="Added roles", value=added_roles, inline=False)
        if not_added_roles:
            embed.add_field(name="Errors", value=not_added_roles, inline=False)

        await ctx.send(embed=embed)

    @role.command(name="remove")
    @core.has_permissions(manage_roles=True)
    @core.bot_has_permissions(manage_roles=True)
    @core.describe(
        target="The member to remove the roles from.",
        roles="The roles (wrapped in quotes), to remove from the member.",
        reason="The reason that will show up in the audit log.",
    )
    async def role_remove(
        self, ctx: Context, target: Target, roles: commands.Greedy[discord.Role], *, reason: Reason = DefaultReason
    ):
        """
        Remove roles from a member.
        """
        errors = []
        for role in roles:
            if role > ctx.me.top_role:
                errors.append(f"{role.mention}: This role is higher than my top role.")
                roles.remove(role)
            elif role == ctx.me.top_role:
                errors.append(f"{role.mention}: This role is equal to my top role.")
                roles.remove(role)
            elif role > ctx.author.top_role:
                errors.append(f"{role.mention}: This role is higher than your top role.")
                roles.remove(role)
            elif role == ctx.author.top_role:
                errors.append(f"{role.mention}: This role is equal to your top role.")
                roles.remove(role)
            elif role not in target.roles:
                errors.append(f"{role.mention}: Member doesn't have this role.")
                roles.remove(role)
            elif role.managed:
                errors.append(f"{role.mention}: Can not remove managed roles.")
                roles.remove(role)

        await target.remove_roles(*roles, reason=reason)
        added_roles = "\n".join(role.mention for role in roles)
        not_added_roles = "\n".join(errors)

        embed = discord.Embed(title=f"Edited {target} roles")
        if added_roles:
            embed.add_field(name="Removed roles", value=added_roles, inline=False)
        if not_added_roles:
            embed.add_field(name="Errors", value=not_added_roles, inline=False)

        await ctx.send(embed=embed)

    @core.command()
    @core.has_permissions(kick_members=True)
    @core.bot_has_permissions(moderate_members=True)
    @core.describe(
        target="Member to timeout",
        duration="How long to timeout the member.",
        reason="Reason that will show up in the audit log.",
    )
    async def timeout(self, ctx: Context, target: Target, duration: Time, *, reason: Reason = DefaultReason):
        """
        Timeout a member in the server.

        Minimum 1 minute, maximum 28 days.
        """
        if duration < 60:
            raise commands.BadArgument("Minimum timeout is 1 minute.")
        if duration > 60 * 60 * 24 * 28:
            raise commands.BadArgument("Maximum timeout is 28 days.")
        if target.is_timed_out():
            raise commands.BadArgument("Member is already timed out.")
        until = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(seconds=duration)
        await target.timeout(until, reason=reason)
        await ctx.send(f"Timed out {target} until {discord.utils.format_dt(until)}.", ephemeral=True)

    @core.command()
    @core.has_permissions(kick_members=True)
    @core.bot_has_permissions(moderate_members=True)
    @core.describe()
    async def untimeout(self, ctx: Context, target: Target, *, reason: Reason = DefaultReason):
        """
        Remove a timeout from a member.
        """
        if not target.is_timed_out():
            raise commands.BadArgument("Member is not timed out.")
        await target.timeout(None, reason=reason)
        await ctx.send(f"Removed timeout from {target}.", ephemeral=True)


async def setup(bot: OiBot) -> None:
    await bot.add_cog(Moderation(bot))
