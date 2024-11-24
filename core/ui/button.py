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

from typing import Callable, TYPE_CHECKING, TypeVar

from discord import ButtonStyle
from discord.ui import Button, View

if TYPE_CHECKING:
    from discord.ui.item import ItemCallbackType


__all__ = ("button",)

V_co = TypeVar("V_co", bound="View", covariant=True)
BT = TypeVar("BT", bound=Button)


def button(
    *,
    cls: type[BT] = Button,
    label: str | None = None,
    custom_id: str | None = None,
    disabled: bool = False,
    style: ButtonStyle = ButtonStyle.secondary,
    emoji: str | None = None,
    row: int | None = None,
) -> Callable[[ItemCallbackType[V_co, BT]], BT]:
    def decorator(func: ItemCallbackType[V_co, BT]) -> ItemCallbackType[V_co, BT]:
        func.__discord_ui_model_type__ = cls
        func.__discord_ui_model_kwargs__ = {
            "style": style,
            "custom_id": custom_id,
            "url": None,
            "disabled": disabled,
            "label": label,
            "emoji": emoji,
            "row": row,
        }
        return func

    return decorator  # type: ignore
