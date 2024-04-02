from __future__ import annotations

import datetime
from typing import Any, Callable, Concatenate, ParamSpec, TYPE_CHECKING, TypeVar

from discord import app_commands
from discord.ext import commands
from discord.utils import MISSING

if TYPE_CHECKING:
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
        super().__init__(*args, **kwargs)
        app_command = getattr(self, "app_command", None)
        if app_command:
            app_command.guild_only = True


class HybridGroup(commands.HybridGroup, Group[CogT, P, T]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        app_command = getattr(self, "app_command", None)
        if app_command:
            app_command.guild_only = True

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
    """
    Normal bot class but with command and group decorators changed to HybridCommand and HybridGroup.
    """

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


describe = app_commands.describe
