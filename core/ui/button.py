from __future__ import annotations

from typing import Any, Callable, Coroutine, TYPE_CHECKING, TypeVar

from discord import ButtonStyle, Interaction
from discord.ui import Button, Item, View

if TYPE_CHECKING:
    from discord.ui.item import ItemCallbackType


__all__ = ("button",)

V = TypeVar("V", bound="View", covariant=True)
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
) -> Callable[[ItemCallbackType[V, BT]], BT]:
    def decorator(func: ItemCallbackType[V, BT]) -> ItemCallbackType[V, BT]:
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
