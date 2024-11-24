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
from typing import (
    Any,
    Callable,
    Concatenate,
    Coroutine,
    Generator,
    Literal,
    overload,
    ParamSpec,
    TYPE_CHECKING,
    TypeVar,
    Union,
)

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import cached_property, MISSING

if TYPE_CHECKING:
    from discord.abc import Snowflake
    from discord.ext.commands import Context
    from discord.ext.commands._types import Coro
    from discord.ext.commands.hybrid import HybridAppCommand

    from .oi import OiBot


__all__ = (
    "Bot",
    "Cog",
    "Command",
    "Group",
    "GroupCog",
    "HybridCommand",
    "HybridGroup",
    "command",
    "describe",
    "group",
)


CogT = TypeVar("CogT", bound="Cog | None")
P = ParamSpec("P")
T = TypeVar("T")
type CommandType = int | app_commands.Command[Any, ..., Any] | HybridCommand[Any, ..., Any] | HybridGroup[Any, ..., Any]


class Command(commands.Command[CogT, P, T]):
    def __init__(
        self,
        func: Callable[Concatenate[CogT, Context[Any], P], Coro[T]] | Callable[Concatenate[Context[Any], P], Coro[T]],
        /,
        **kwargs: Any,
    ) -> None:
        extras: dict[Any, Any] = kwargs.get("extras", {})
        self.member_permissions: list[str] = getattr(func, "__member_permissions__", extras.get("member_permissions", []))
        self.member_guild_permissions: list[str] = getattr(
            func, "__member_guild_permissions__", extras.get("member_guild_permissions", [])
        )
        self.bot_permissions: list[str] = getattr(func, "__bot_permissions__", extras.get("bot_permissions", []))
        self.bot_guild_permissions: list[str] = getattr(
            func, "__bot_guild_permissions__", extras.get("bot_guild_permissions", [])
        )
        super().__init__(func, **kwargs)

    def __repr__(self) -> str:
        return f"<Command name={self.name}>"

    @property
    def signature(self) -> str:
        params = self.clean_params
        if not params:
            return ""

        result = []
        for param in params.values():
            name = param.displayed_name or param.name

            greedy = isinstance(param.converter, commands.Greedy)
            optional = False

            annotation: Any = param.converter.converter if greedy else param.converter
            origin = getattr(annotation, "__origin__", None)
            if not greedy and origin is Union:
                none_cls = type(None)
                union_args = annotation.__args__
                optional = union_args[-1] is none_cls
                if len(union_args) == 2 and optional:
                    annotation = union_args[0]
                    origin = getattr(annotation, "__origin__", None)

            if annotation is discord.Attachment:
                if optional:
                    result.append(f"[{name} (upload a file)]")
                elif greedy:
                    result.append(f"[{name} (upload files)]")
                else:
                    result.append(f"<{name} (upload a file)>")
                continue

            # Original implementation shows union arguments, we don't need it.
            # It also shows displayed defaults, but we don't need it because
            # it is shown elsewhere (in the help command).
            if not param.required:
                result.append(f"[{name}]")

            elif param.kind == param.VAR_POSITIONAL:
                if self.require_var_positional:
                    result.append(f"<{name}...>")
                else:
                    result.append(f"[{name}...]")
            elif greedy:
                result.append(f"[{name}]...")
            elif optional:
                result.append(f"[{name}]")
            else:
                result.append(f"<{name}>")

        return " ".join(result)


class Group(commands.Group, Command[CogT, P, T]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<Group name={self.name}>"

    def command(self, name: str = MISSING, **attrs: Any) -> Callable[..., Command | HybridCommand]:
        def decorator(func):
            attrs.setdefault("parent", self)
            result = command(name=name, **attrs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(self, name: str = MISSING, **attrs: Any) -> Callable[..., Group | HybridGroup]:
        def decorator(func):
            attrs.setdefault("parent", self)
            result = group(name=name, **attrs)(func)
            self.add_command(result)
            return result

        return decorator


class Mention:
    def __init__(self, command: HybridCommand[Any, ..., Any] | HybridGroup[Any, ..., Any], /) -> None:
        self.command = command
        try:
            self.tree: MentionableTree = command.cog.bot.tree
        except AttributeError as exc:
            raise ValueError("Can not mention command that doesn't have a tree.") from exc

    def get_mention(self, /, *, guild: Snowflake | None = None) -> str:
        default = f"/{self.command.qualified_name}"
        if not self.command.app_command:
            return default
        command = self.command.app_command
        if isinstance(self.command, HybridGroup) and self.command.fallback:
            cmd = self.command.app_command.get_command(self.command.fallback)
            if cmd:
                command = cmd
        mention = self.tree.get_mention(command, guild=guild)
        if not mention:
            return default
        return mention

    def __call__(self, /, *, guild: Snowflake | None):
        return self.get_mention(guild=guild)

    def __str__(self):
        return self.get_mention()


class HybridCommand(commands.HybridCommand, Command[CogT, P, T]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if self.app_command:
            self.app_command.guild_only = True

    @cached_property
    def mention(self) -> Mention:
        return Mention(self)

    @cached_property
    def id(self) -> int | None:
        try:
            tree: MentionableTree = self.cog.bot.tree

            app_command = tree.get_app_command(self)
            if app_command:
                return app_command.id
        except AttributeError:
            return None


class HybridGroup(commands.HybridGroup, Group[CogT, P, T]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.app_command:
            self.app_command.guild_only = True

    @cached_property
    def mention(self):
        return Mention(self)

    @cached_property
    def id(self) -> int | None:
        try:
            tree: MentionableTree = self.cog.bot.tree

            app_command = tree.get_app_command(self)
            if app_command:
                return app_command.id
        except AttributeError:
            return None

    def command(
        self,
        name: str = MISSING,
        *args: Any,
        with_app_command: bool = True,
        **kwargs: Any,
    ) -> Callable[..., HybridCommand[CogT, P, T]]:
        def decorator(func):
            kwargs.setdefault("parent", self)
            result = command(name=name, *args, with_app_command=with_app_command, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(
        self,
        name: str = MISSING,
        *args: Any,
        with_app_command: bool = True,
        **kwargs: Any,
    ) -> Callable[..., HybridGroup[CogT, P, T]]:
        def decorator(func):
            kwargs.setdefault("parent", self)
            result = group(name=name, *args, with_app_command=with_app_command, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def get_command(
        self, name
    ) -> HybridCommand[Any, ..., Any] | Command[Any, ..., Any] | commands.Command[Any, ..., Any] | None:
        return super().get_command(name)


def command(name: str = MISSING, **attrs: Any) -> Callable[..., HybridCommand]:
    def decorator(func) -> HybridCommand:
        if isinstance(func, HybridCommand):
            raise TypeError("Callback is already a command.")
        return HybridCommand(func, name=name, **attrs)

    return decorator


def group(name: str = MISSING, **attrs: Any) -> Callable[..., HybridGroup]:
    def decorator(func) -> HybridGroup:
        if isinstance(func, HybridGroup):
            raise TypeError("Callback is already a group.")
        return HybridGroup(func, name=name, **attrs)

    return decorator


class Cog(commands.Cog):
    def __init__(self, bot: OiBot) -> None:
        self.bot: OiBot = bot
        self.load_time: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    def __repr__(self) -> str:
        return f"<Cog name={self.qualified_name}>"

    @property
    def display_emoji(self) -> str:
        return "<:oi_coin:909746036996702239>"


class GroupCog(commands.GroupCog):
    def __init__(self, bot: OiBot) -> None:
        self.bot: OiBot = bot
        self.load_time: datetime.datetime = datetime.datetime.now(tz=datetime.timezone.utc)

    def __repr__(self) -> str:
        return f"<GroupCog name={self.qualified_name}>"

    @property
    def display_emoji(self) -> str:
        return "<:oi_coin:909746036996702239>"


class MentionableTree(app_commands.CommandTree):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.application_commands: dict[int | None, list[app_commands.AppCommand]] = {}
        self.cache: dict[int | None, dict[app_commands.Command | app_commands.Group | HybridCommand | str, str]] = {}

    async def sync(self, *, guild: Snowflake | None = None) -> list[app_commands.AppCommand]:
        """Syncs all application commands under this tree to Discord, then caches the commands."""
        ret = await super().sync(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = ret
        self.cache.pop(guild_id, None)
        return ret

    async def fetch_commands(self, *, guild: Snowflake | None = None) -> list[app_commands.AppCommand]:
        """Fetches app commands from Discord, then caches the commands."""
        ret = await super().fetch_commands(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = ret
        self.cache.pop(guild_id, None)
        return ret

    def get_app_commands(self, *, guild: Snowflake | None = None):
        """Returns the cached app commands, if any."""
        try:
            return self.application_commands[guild.id if guild else None]
        except KeyError:
            return None

    async def get_or_fetch_app_commands(self, *, guild: Snowflake | None = None):
        """Method overwritten to store the commands."""
        try:
            return self.application_commands[guild.id if guild else None]
        except KeyError:
            return await self.fetch_commands(guild=guild)

    @overload
    def get_app_command(
        self, command: CommandType, *, guild: Snowflake | None = None, fetch: Literal[True]
    ) -> Coroutine[Any, Any, app_commands.AppCommand | None]: ...

    @overload
    def get_app_command(
        self, command: CommandType, *, guild: Snowflake | None = None, fetch: Literal[False] = ...
    ) -> app_commands.AppCommand | None: ...

    def get_app_command(
        self, command: CommandType, *, guild: Snowflake | None = None, fetch: bool = False
    ) -> Coroutine[Any, Any, app_commands.AppCommand | None] | app_commands.AppCommand | None:
        check_global = self.fallback_to_global is True and guild is not None
        if fetch:

            async def _async() -> app_commands.AppCommand | None:
                if isinstance(command, int):
                    try:
                        return await self.fetch_command(command, guild=guild)
                    except discord.NotFound:
                        return None
                local_commands = await self.get_or_fetch_app_commands(guild=guild)
                app_command_found = discord.utils.get(local_commands, name=(command.root_parent or command).name)

                if check_global and not app_command_found:
                    global_commands = await self.get_or_fetch_app_commands(guild=guild)
                    app_command_found = discord.utils.get(global_commands, name=(command.root_parent or command).name)
                return app_command_found

            return _async()

        def _sync() -> app_commands.AppCommand | None:
            empty = []
            if isinstance(command, int):
                local_commands = self.get_app_commands(guild=guild) or empty
                app_command_found = discord.utils.get(local_commands, id=command)

                if check_global and not app_command_found:
                    global_commands = self.get_app_commands(guild=None) or empty
                    app_command_found = discord.utils.get(global_commands, id=command)
                return app_command_found

            local_commands = self.get_app_commands(guild=guild) or empty
            app_command_found = discord.utils.get(local_commands, name=(command.root_parent or command).name)

            if check_global and not app_command_found:
                global_commands = self.get_app_commands(guild=None) or empty
                app_command_found = discord.utils.get(global_commands, name=(command.root_parent or command).name)
            return app_command_found

        return _sync()

    async def fetch_mention(
        self, command: app_commands.Command | HybridCommand, *, guild: Snowflake | None = None
    ) -> str | None:
        """Fetches the mention of an AppCommand given a specific command name, and optionally, a guild.

        Parameters
        ----------
        name: `app_commands.Command` | `HybridCommand`
            The command to retrieve the mention for.
        guild: `Snowflake` | `None`
            The scope (guild) from which to retrieve the commands from. If None is given or not passed,
            only the global scope will be searched, however the global scope will also be searched if
            a guild is passed.

        Returns
        -------
        str | None
            The command mention, if found.
        """
        guild_id = guild.id if guild else None
        try:
            return self.cache[guild_id][command]
        except KeyError:
            pass

        check_global = self.fallback_to_global is True and guild is not None

        local_commands = await self.get_or_fetch_app_commands(guild=guild)
        app_command_found = discord.utils.get(local_commands, name=(command.root_parent or command).name)

        if check_global and not app_command_found:
            global_commands = await self.get_or_fetch_app_commands(guild=None)
            app_command_found = discord.utils.get(global_commands, name=(command.root_parent or command).name)

        if not app_command_found:
            return None

        mention = f"</{command.qualified_name}:{app_command_found.id}>"
        self.cache.setdefault(guild_id, {})
        self.cache[guild_id][command] = mention
        return mention

    def get_mention(
        self,
        command: app_commands.Command | app_commands.Group | HybridCommand | HybridAppCommand,
        *,
        guild: Snowflake | None = None,
    ) -> str | None:
        """Retrieves the mention of an AppCommand given a specific command name from cache, and optionally, a guild.

        Parameters
        ----------
        name: `app_commands.Command` | `HybridCommand`
            The command to retrieve the mention for.
        guild: `Snowflake` | `None`
            The scope (guild) from which to retrieve the commands from. If None is given or not passed,
            only the global scope will be searched, however the global scope will also be searched if
            a guild is passed.

        Returns
        -------
        str | None
            The command mention, if found.
        """

        guild_id = guild.id if guild else None
        try:
            return self.cache[guild_id][command]
        except KeyError:
            pass

        # If a guild is given, and fallback to global is set to True, then we must also
        # check the global scope, as commands for both show in a guild.
        check_global = self.fallback_to_global is True and guild is not None

        local_commands = self.get_app_commands(guild=guild)
        if not local_commands:
            return None
        app_command_found = discord.utils.get(local_commands, name=(command.root_parent or command).name)

        if check_global and not app_command_found:
            global_commands = self.get_app_commands(guild=None)
            if not global_commands:
                return None
            app_command_found = discord.utils.get(global_commands, name=(command.root_parent or command).name)

        if not app_command_found:
            return None

        mention = f"</{command.qualified_name}:{app_command_found.id}>"
        self.cache.setdefault(guild_id, {})
        self.cache[guild_id][command] = mention
        return mention

    def _walk_children(
        self, commands: list[app_commands.Group | app_commands.Command]
    ) -> Generator[app_commands.Command, None, None]:
        for command in commands:
            if isinstance(command, app_commands.Group):
                yield from self._walk_children(command.commands)
            else:
                yield command

    async def __async_walk_mentions(self, *, guild: Snowflake | None = None):
        for command in self._walk_children(self.get_commands(guild=guild, type=discord.AppCommandType.chat_input)):
            mention = await self.fetch_mention(command, guild=guild)
            if mention:
                yield command, mention
        if guild and self.fallback_to_global is True:
            for command in self._walk_children(self.get_commands(guild=None, type=discord.AppCommandType.chat_input)):
                mention = await self.fetch_mention(command, guild=guild)
                if mention:
                    yield command, mention

    def __walk_mentions(self, *, guild: Snowflake | None = None):
        for command in self._walk_children(self.get_commands(guild=guild, type=discord.AppCommandType.chat_input)):
            mention = self.get_mention(command, guild=guild)
            if mention:
                yield command, mention
        if guild and self.fallback_to_global is True:
            for command in self._walk_children(self.get_commands(guild=None, type=discord.AppCommandType.chat_input)):
                mention = self.get_mention(command, guild=guild)
                if mention:
                    yield command, mention

    def walk_mentions(self, *, guild: Snowflake | None = None, fetch: bool = False):
        """Gets all valid mentions for app commands in a specific guild.

        This takes into consideration group commands, it will only return mentions for
        the command's children, and not the parent as parents aren't mentionable.

        Parameters
        ----------
        guild: discord.Guild | None
            The guild to get commands for. If not given, it will only return global commands.
        fetch: bool
            Whether to fetch the commands. This will return a corutine.

        Yields
        ------
        tuple[`app_commands.Command` | `HybridCommand`, str]

        """
        if fetch:
            return self.__async_walk_mentions(guild=guild)
        return self.__walk_mentions(guild=guild)


type CommandGroupUnion = (
    commands.Command[Any, ..., Any]
    | commands.Group[Any, ..., Any]
    | Command[Any, ..., Any]
    | Group[Any, ..., Any]
    | HybridCommand[Any, ..., Any]
    | HybridGroup[Any, ..., Any]
)


class Bot(commands.AutoShardedBot):
    """AutoShardedBot with a custom tree, command, and group decorators."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs, tree_cls=MentionableTree)

    def command(self, name: str = MISSING, **kwargs) -> Callable[..., HybridCommand]:
        def decorator(func) -> HybridCommand:
            if isinstance(func, Command):
                raise TypeError("Callback is already a command.")
            cmd = HybridCommand(func, name=name, **kwargs)
            self.add_command(cmd)
            return cmd

        return decorator

    def group(self, name: str = MISSING, **kwargs) -> Callable[..., HybridGroup]:
        def decorator(func) -> HybridGroup:
            if isinstance(func, Group):
                raise TypeError("Callback is already a group.")
            cmd = HybridGroup(func, name=name, **kwargs)
            self.add_command(cmd)
            return cmd

        return decorator

    def walk_commands(
        self,
    ) -> Generator[CommandGroupUnion, None, None]:
        return super().walk_commands()

    def get_command(self, name: str) -> CommandGroupUnion | None:
        return super().get_command(name)


describe = app_commands.describe
