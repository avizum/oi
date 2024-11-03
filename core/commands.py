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
from typing import Any, Callable, Concatenate, Generator, ParamSpec, TYPE_CHECKING, TypeVar, Union

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING

if TYPE_CHECKING:
    from discord.app_commands import AppCommand
    from discord.ext.commands import Context
    from discord.ext.commands._types import Coro

    from .oi import OiBot


__all__ = (
    "Bot",
    "Cog",
    "Command",
    "command",
    "describe",
    "Group",
    "group",
    "GroupCog",
    "HybridCommand",
    "HybridGroup",
)


CogT = TypeVar("CogT", bound="Cog | None")
P = ParamSpec("P")
T = TypeVar("T")


class Command(commands.Command[CogT, P, T]):
    def __init__(
        self,
        func: Callable[Concatenate[CogT, Context[Any], P], Coro[T]] | Callable[Concatenate[Context[Any], P], Coro[T]],
        /,
        **kwargs: Any,
    ) -> None:
        extras = kwargs.get("extras", {})
        self.member_permissions: list[str] | None = getattr(func, "__member_permissions__", extras.get("member_permissions"))
        self.member_guild_permissions: list[str] | None = getattr(
            func, "__member_guild_permissions__", extras.get("member_guild_permissions")
        )
        self.bot_permissions: list[str] | None = getattr(func, "__bot_permissions__", extras.get("bot_permissions"))
        self.bot_guild_permissions: list[str] | None = getattr(
            func, "__bot_guild_permissions__", extras.get("bot_guild_permissions")
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


class HybridCommand(commands.HybridCommand, Command[CogT, P, T]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.raw_app_command: AppCommand | None = None
        super().__init__(*args, **kwargs)

        if self.app_command:
            self.app_command.guild_only = True

    @property
    def mention(self):
        if not self.raw_app_command:
            return f"/{self.qualified_name}"
        return self.raw_app_command.mention


class HybridGroup(commands.HybridGroup, Group[CogT, P, T]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.raw_app_command: AppCommand | None = None
        super().__init__(*args, **kwargs)
        if self.app_command:
            self.app_command.guild_only = True

    @property
    def mention(self):
        if not self.raw_app_command:
            return f"/{self.qualified_name}"
        return self.raw_app_command.mention

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


class Bot(commands.AutoShardedBot):
    """Normal bot class but with command and group decorators changed to HybridCommand and HybridGroup."""

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
    ) -> Generator[HybridCommand[Any, ..., Any] | HybridGroup[Any, ..., Any] | commands.Command[Any, ..., Any], None, None]:
        return super().walk_commands()

    def get_command(
        self, name: str
    ) -> HybridCommand[Any, ..., Any] | HybridGroup[Any, ..., Any] | commands.Command[Any, ..., Any] | None:
        return super().get_command(name)


describe = app_commands.describe
