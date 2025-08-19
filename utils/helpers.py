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

import math
from typing import Any, ClassVar, Sequence, TYPE_CHECKING

import discord
from discord import ui

if TYPE_CHECKING:
    from core import Context

__all__ = (
    "ANSIFormat",
    "embed_to_text",
    "format_seconds",
    "readable_bytes",
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


def embed_to_container(embed: discord.Embed) -> ui.Container:
    """Converts a `discord.Embed` to a `discord.ui.Container`.

    This is used as a helper to easilly convert to the Components V2.

    Author and Footer fields will not render icon urls. This is a Discord limitation.

    """
    container = ui.Container()
    container.accent_color = embed.color

    if embed.author and embed.author.name:
        container.add_item(ui.TextDisplay(f"-# **{embed.author.name}**"))

    if embed.title or embed.description:
        title = f"### {embed.title}" or ""
        description = embed.description or ""
        if title or description:
            if embed.thumbnail and embed.thumbnail.url:
                container.add_item(ui.Section(*[title, description], accessory=ui.Thumbnail(embed.thumbnail.url)))
            else:
                container.add_item(ui.TextDisplay(f"{title}\n{description}"))

    for field in embed.fields:
        container.add_item(ui.TextDisplay(f"**{field.name}**\n{field.value}"))

    if embed.footer and embed.footer.text:
        container.add_item(ui.TextDisplay(f"-# {embed.footer.text}"))

    return container


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


def readable_bytes(size_in_bytes: int) -> str:
    """Converts
    E.g.:
        1000 -> 1.00 KB
        12345678 -> 12.34 MB
    """
    units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")

    power = int(math.log(max(abs(size_in_bytes), 1), 1000))

    return f"{size_in_bytes / (1000 ** power):.2f} {units[power]}"


class ANSIFormat:
    PRE = "\x1b["
    END = f"{PRE}0m"
    SEP = ";"
    MAPPING: ClassVar[dict[str, str]] = {
        # Normal text colors
        "k": "30",  # black
        "r": "31",  # red
        "g": "32",  # green
        "y": "33",  # yellow
        "b": "34",  # blue
        "m": "35",  # magenta
        "c": "36",  # cyan
        "w": "37",  # white
        # Bright text colors
        "K": "90",
        "R": "91",
        "G": "92",
        "Y": "93",
        "B": "94",
        "M": "95",
        "C": "96",
        "W": "97",
        # Background Colors (same as above but with 'bg' as a prefix)
        "bgk": "40",
        "bgr": "41",
        "bgg": "42",
        "bgy": "43",
        "bgb": "44",
        "bgm": "45",
        "bgc": "46",
        "bgw": "47",
        # Bright background colors
        "bgK": "100",
        "bgR": "101",
        "bgG": "102",
        "bgY": "103",
        "bgB": "104",
        "bgM": "105",
        "bgC": "106",
        "bgW": "107",
        # Text formatting
        "**": "1",  # bold
        "d": "2",  # dim
        "*": "3",  # italic
        "_": "4",  # underline
        "+": "5",  # blink
        "++": "6",  # rapid blink
        "!": "7",  # inverse
        "|": "8",  # hide
        "~": "9",  # strikethrough
    }

    def __init__(self, text: Any, /) -> None:
        self.text: str = str(text)

    def __format__(self, format_spec: str) -> str:
        # Split the format_spec if there are multiple specifiers
        format_keys = format_spec.split(self.SEP)

        # Translate each key to its corresponding ANSI code
        codes = [self.MAPPING[key] for key in format_keys if key in self.MAPPING]

        # If no valid codes, return the text as-is
        if not codes:
            return self.text

        # Combine codes into a single ANSI sequence
        ansi_start = f"{self.PRE}{self.SEP.join(codes)}m"
        return f"{ansi_start}{self.text}{self.END}"
