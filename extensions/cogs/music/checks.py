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

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from .types import PlayerContext


__all__ = (
    "is_in_voice",
    "is_in_channel",
    "is_not_deafened",
    "is_manager",
)


def is_in_voice(*, author: bool = True, bot: bool = True):
    """Checks if a member or bot is in the voice channel."""

    def inner(ctx: PlayerContext) -> bool:
        if author and bot:
            if ctx.author.voice and ctx.voice_client and ctx.author.voice.channel == ctx.voice_client.channel:
                return True
            elif ctx.voice_client and not ctx.author.voice:
                raise commands.CheckFailure(
                    f"You need to be connected to {ctx.voice_client.channel.mention} to use this command."
                )
            else:
                raise commands.CheckFailure("There is no music player connected.")
        elif author:
            if ctx.author.voice:
                return True
            raise commands.CheckFailure("You need to be connected to a voice channel to use this command.")
        elif bot:
            if ctx.voice_client:
                return True
            raise commands.CheckFailure("There is no music player connected.")
        raise commands.CheckFailure("Uh oh.")

    return commands.check(inner)


def is_in_channel():
    """Checks if the current channel is the bound channel."""

    def inner(ctx: PlayerContext) -> bool:
        vc = ctx.voice_client
        if vc and ctx.channel != vc.ctx.channel:
            raise commands.CheckFailure(f"This command can only be ran in {vc.ctx.channel.mention}, not here.")
        return True

    return commands.check(inner)


def is_not_deafened():
    """Checks if a member is deafened."""

    def inner(ctx: PlayerContext) -> bool:
        voice = ctx.author.voice
        if voice and voice.self_deaf:
            raise commands.CheckFailure("You can not use this command while deafened.")
        return True

    return commands.check(inner)


def is_manager():
    """
    Checks if a member is a player "manager".

    Manager is determined as follows:
    - If DJ is disabled, anyone is a manager.
    - If DJ is enabled and:
        - DJ role is enabled, anyone with DJ role is a manager.
        - DJ role is disabled, the first user of a session is a manager.
    Note: Anybody with Manage Guild permissions is alawys a manager.
    """

    def inner(ctx: PlayerContext) -> bool:
        vc = ctx.voice_client

        if not vc.dj_enabled or ctx.author.guild_permissions.manage_guild:
            return True

        if vc.dj_role:
            if vc.dj_role in ctx.author.roles:
                return True
            raise commands.CheckFailure(
                f"You need to have {vc.dj_role.mention} role or have `Manage Server` permissions to do this."
            )
        elif not vc.dj_role:
            if vc.manager == ctx.author:
                return True
            raise commands.CheckFailure("You need to be DJ or have `Manage Server` permission to do this.")

        return True

    return commands.check(inner)
