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

from typing import Sequence, TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from core import Context

__all__ = (
    "embed_to_text",
    "format_seconds",
)


def embed_to_text(embed: discord.Embed) -> str:
    """Converts an embed to a string.

    Only provides the title, description, fields, footer, and image.
    """
    output = []
    if embed.title:
        output.append(f"**{embed.title}**\n")
    if embed.description:
        output.append(embed.description)
    output.append("\n")

    for field in embed.fields:
        output.extend((f"**{field.name}**\n", field.value))

    if embed.image:
        output.append(f"\n{embed.image.url}")

    if embed.footer:
        output.append(f"\n-# {embed.footer.text}")

    return "\n".join(output)


def _format_embeds(ctx: Context, embeds: Sequence[discord.Embed]) -> Sequence[discord.Embed]:
    """Formats embeds so that they all look uniform. Changes the color of all embeds."""
    for embed in embeds:
        if not embed.color:
            embed.color = 0x00FFB3
    return embeds


# from https://github.com/Axelancerr/Life/blob/508e1e9c5b02f56f76a53a2cfd9b521ddacdd8f3/Life/utilities/utils.py#L51-L64
def format_seconds(seconds: float, *, friendly: bool = False) -> str:
    """Converts time in seconds to a readable string.

    Ex: 300 -> 05:00 or 5m 0s if friendly is True
    """
    seconds = round(seconds)

    minute, second = divmod(seconds, 60)
    hour, minute = divmod(minute, 60)
    day, hour = divmod(hour, 24)

    days, hours, minutes, seconds = (
        round(day),
        round(hour),
        round(minute),
        round(second),
    )

    if friendly:
        day = f"{days}d " if days != 0 else ""
        hour = f"{hours}h " if hours != 0 or days != 0 else ""
        minsec = f"{minutes}m {seconds}s"
        return f"{day}{hour}{minsec}"
    day = f"{days:02d}:" if days != 0 else ""
    hour = f"{hours:02d}:" if hours != 0 or days != 0 else ""
    minsec = f"{minutes:02d}:{seconds:02d}"
    return f"{day}{hour}{minsec}"
