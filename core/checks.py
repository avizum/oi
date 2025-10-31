"""
GPL-3.0 LICENSE

Some of the contents of this file is taken from:
https://github.com/avizum/alpine/blob/f50ae4edd27ddac7e9913c113a2f898ac4da0332/core/checks.py

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

import functools
import inspect
from typing import Any, Callable, Coroutine, TYPE_CHECKING, TypeVar

import discord
from discord.ext import commands

from utils import NotVoted

from .commands import Command

if TYPE_CHECKING:
    from discord.ext.commands._types import Check, ContextT, UserCheck

    from .context import Context


__all__ = (
    "bot_has_guild_permissions",
    "bot_has_permissions",
    "check",
    "has_guild_permissions",
    "has_permissions",
    "has_voted",
    "is_owner",
)


T = TypeVar("T")
Coro = Coroutine[Any, Any, T]
CoroFunc = Callable[..., Coro[Any]]
CommandCoro = Command[Any, ..., Any] | CoroFunc


def check(predicate: UserCheck[ContextT]) -> Check[ContextT]:
    def decorator(func: Command[Any, ..., Any] | CoroFunc) -> Command[Any, ..., Any] | CoroFunc:
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
        else:
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []

            func.__commands_checks__.append(predicate)

        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: ContextT):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator  # type: ignore


def has_permissions(**perms: bool) -> Callable[[CommandCoro], CommandCoro]:
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    def predicate(ctx: Context[Any]) -> bool:
        permissions = ctx.permissions

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]

        if not missing:
            return True

        raise commands.MissingPermissions(missing)

    def decorator(func: CommandCoro) -> CommandCoro:
        permissions = [perm for perm, value in perms.items() if value]
        app_command_permissions = discord.Permissions(**perms)
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
            func.member_permissions = permissions
            if getattr(func, "__commands_is_hybrid__", None):
                app_command = getattr(func, "app_command", None)
                if app_command:
                    app_command.default_permissions = app_command_permissions
        else:
            if not hasattr(func, "__member_permissions__"):
                func.__member_permissions__ = []
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []
            func.__member_permissions__.extend(permissions)
            func.__commands_checks__.append(predicate)
            func.__discord_app_commands_default_permissions__ = app_command_permissions

        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def has_guild_permissions(**perms: bool) -> Callable[[CommandCoro], CommandCoro]:
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    def predicate(ctx: Context[Any]) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage

        permissions = ctx.author.guild_permissions  # type: ignore
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]

        if not missing:
            return True

        raise commands.MissingPermissions(missing)

    def decorator(func: CommandCoro) -> CommandCoro:
        permissions = [perm for perm, value in perms.items() if value]
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
            func.member_guild_permissions = permissions
        else:
            if not hasattr(func, "__member_guild_permissions__"):
                func.__member_guild_permissions__ = []
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []
            func.__member_guild_permissions__.extend(permissions)
            func.__commands_checks__.append(predicate)

        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def bot_has_permissions(**perms: bool) -> Callable[[CommandCoro], CommandCoro]:
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    def predicate(ctx: Context[Any]) -> bool:
        permissions = ctx.bot_permissions

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]

        if not missing:
            return True

        raise commands.BotMissingPermissions(missing)

    def decorator(func: CommandCoro) -> CommandCoro:
        permissions = [perm for perm, value in perms.items() if value]
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
            func.member_permissions = permissions
        else:
            if not hasattr(func, "__bot_permissions__"):
                func.__bot_permissions__ = []
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []
            func.__bot_permissions__.extend(permissions)
            func.__commands_checks__.append(predicate)

        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def bot_has_guild_permissions(**perms: bool) -> Callable[[CommandCoro], CommandCoro]:
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    def predicate(ctx: Context[Any]) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage

        permissions = ctx.author.guild_permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]

        if not missing:
            return True

        raise commands.BotMissingPermissions(missing)

    def decorator(func: CommandCoro) -> CommandCoro:
        permissions = [perm for perm, value in perms.items() if value]
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
            func.bot_guild_permissions = permissions
        else:
            if not hasattr(func, "__bot_guild_permissions__"):
                func.__bot_guild_permissions__ = []
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []
            func.__bot_guild_permissions__.extend(permissions)
            func.__commands_checks__.append(predicate)

        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def is_owner() -> Callable[[CommandCoro], CommandCoro]:
    async def predicate(ctx: Context) -> bool:
        if not await ctx.bot.is_owner(ctx.author):
            raise commands.NotOwner("You do not own this bot.")
        return True

    def decorator(func: CommandCoro) -> CommandCoro:
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
            func.member_permissions = ["bot_owner"]
        else:
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []
            func.__commands_checks__.append(predicate)
            if not hasattr(func, "__member_permissions__"):
                func.__member_permissions__ = []
            func.__member_permissions__.append("bot_owner")
        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def has_voted() -> Callable[[CommandCoro], CommandCoro]:
    async def predicate(ctx: Context) -> bool:
        bot = ctx.bot

        if await bot.is_owner(ctx.author):
            return True

        if ctx.author not in bot.votes:
            check = await bot.topgg.has_voted(ctx.author.id)
            bot.votes[ctx.author.id] = check
            if not check:
                raise NotVoted()
            return True
        return False

    def decorator(func: CommandCoro) -> CommandCoro:
        if isinstance(func, Command):
            func.checks.append(predicate)  # type: ignore
            func.member_permissions = ["to_vote"]
        else:
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []
            func.__commands_checks__.append(predicate)
            if not hasattr(func, "__member_permissions__"):
                func.__member_permissions__ = []
            func.__member_permissions__.append("to_vote")
        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator
