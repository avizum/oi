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

from discord.ext import commands

__all__ = (
    "Blacklisted",
    "Maintenance",
    "NotVoted",
)


class NotVoted(commands.CheckFailure):
    """Raised when a user has not voted for the bot."""


class Maintenance(commands.CheckFailure):
    """Raised when bot is under maintenance."""


class Blacklisted(commands.CheckFailure):
    """Raised when a user is blacklisted."""

    def __init__(self, /, *, moderator: str, reason: str, permanent: bool):
        self.moderator: str = moderator
        self.reason: str = reason
        self.permanent: bool = permanent
