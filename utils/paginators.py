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

import contextlib
from typing import Any, TYPE_CHECKING

import discord
from discord.ext import menus

if TYPE_CHECKING:
    from core import Context


class SkipPage(discord.ui.Modal, title="Skip to page"):
    to_page = discord.ui.TextInput(label="Place holder")

    def __init__(self, timeout: float | None, view: Paginator):
        super().__init__(timeout=timeout)
        self.view = view
        self.to_page.label = f"Enter page number: 1-{self.view.source.get_max_pages()}"
        self.to_page.min_length = 1
        self.to_page.max_length = len(str(self.view.source.get_max_pages()))

    async def send_error(self, interaction: discord.Interaction, error: str):
        return await interaction.response.send_message(error, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if not self.to_page.value:
                raise ValueError("Page number cannot be empty.")
            page_num = int(self.to_page.value)
            max_pages = self.view.source.get_max_pages()
            await self.view.show_checked_page(interaction, int(self.to_page.value) - 1)
            if max_pages and page_num > max_pages or page_num <= 0:
                await self.send_error(
                    interaction,
                    f"Please enter a page number between 1 and {max_pages}.",
                )
        except ValueError:
            return await self.send_error(interaction, "Please enter a number.")


class Paginator(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        *,
        ctx: Context,
        timeout: float | None = 180.0,
        check_embeds: bool = True,
        delete_message_after: bool = False,
        remove_view_after: bool = False,
        disable_view_after: bool = True,
        message: discord.Message | None = None,
    ):
        super().__init__(timeout=timeout)
        self.source: menus.PageSource = source
        self.ctx: Context = ctx
        self.check_embeds: bool = check_embeds
        self.delete_message_after: bool = delete_message_after
        self.remove_view_after: bool = remove_view_after
        self.message: discord.Message | None = message
        self.current_page: int = 0
        self.clear_items()
        self._fill_items()

    async def interaction_check(self, itn: discord.Interaction, /) -> bool:
        if itn.user.id != self.ctx.author.id:
            await itn.response.send_message("You can not use this menu.", ephemeral=True)
            return False
        return True

    def _fill_items(self) -> None:
        if self.source.is_paginating():
            self.add_item(self.go_to_first_page)
            self.add_item(self.go_to_previous_page)
            self.add_item(self.show_current_page)
            self.add_item(self.go_to_next_page)
            self.add_item(self.go_to_last_page)
        self.add_item(self.stop_view)

    async def _update(self, page: int) -> None:
        current_page = self.current_page + 1
        max_pages = self.source.get_max_pages()

        self.go_to_first_page.disabled = False
        self.go_to_previous_page.disabled = False
        self.go_to_next_page.disabled = False
        self.go_to_last_page.disabled = False
        self.show_current_page.disabled = False

        if page == 0:
            self.go_to_first_page.disabled = True
            self.go_to_previous_page.disabled = True
        if page == 1:
            self.go_to_first_page.disabled = True
        if page + 1 == max_pages:
            self.go_to_next_page.disabled = True
            self.go_to_last_page.disabled = True
        if page + 2 == max_pages:
            self.go_to_last_page.disabled = True

        self.show_current_page.label = f"{current_page}/{max_pages}"
        self.go_to_first_page.label = "1"
        self.go_to_last_page.label = str(max_pages)

    async def _get_kwargs(self, page: int) -> dict[str, Any]:
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)  # type: ignore
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}
        else:
            return {}

    async def on_timeout(self) -> None:
        if not self.message:
            return
        with contextlib.suppress(discord.NotFound, discord.Forbidden):
            if self.delete_message_after:
                await self.message.delete()
            elif self.remove_view_after:
                await self.message.edit(view=None)

    async def show_page(self, itn: discord.Interaction, page_num: int):
        page = await self.source.get_page(page_num)
        self.current_page = page_num
        kwargs = await self._get_kwargs(page)
        await self._update(page_num)

        if itn.response.is_done():
            if self.message:
                await self.message.edit(view=self, **kwargs)
        else:
            await itn.response.edit_message(view=self, **kwargs)

    async def show_checked_page(self, itn: discord.Interaction, page_num: int):
        max_pages = self.source.get_max_pages()
        try:
            if max_pages is None:
                await self.show_page(itn, page_num)
            elif max_pages > page_num >= 0:
                await self.show_page(itn, page_num)
        except IndexError:
            pass

    async def start(self) -> discord.Message:
        await self.source._prepare_once()
        page = await self.source.get_page(self.current_page)
        kwargs = await self._get_kwargs(page)
        await self._update(self.current_page)
        self.message = await self.ctx.send(**kwargs, view=self)
        return self.message

    @discord.ui.button(emoji="<:skip_left:1294459900696461364>", style=discord.ButtonStyle.grey)
    async def go_to_first_page(self, itn: discord.Interaction, _: discord.ui.Button):
        await self.show_page(itn, 0)

    @discord.ui.button(emoji="<:left:1294459831733719100>", style=discord.ButtonStyle.grey)
    async def go_to_previous_page(self, itn: discord.Interaction, _: discord.ui.Button):
        await self.show_checked_page(itn, self.current_page - 1)

    @discord.ui.button(label="0/0", style=discord.ButtonStyle.blurple)
    async def show_current_page(self, itn: discord.Interaction, _: discord.ui.Button):
        await itn.response.send_modal(SkipPage(self.timeout, self))

    @discord.ui.button(emoji="<:right:1294459762007871611>", style=discord.ButtonStyle.grey)
    async def go_to_next_page(self, itn: discord.Interaction, _: discord.ui.Button):
        await self.show_checked_page(itn, self.current_page + 1)

    @discord.ui.button(emoji="<:skip_right:1294459785130934293>", style=discord.ButtonStyle.grey)
    async def go_to_last_page(self, itn: discord.Interaction, _: discord.ui.Button):
        await self.show_page(itn, self.source.get_max_pages() - 1)  # type: ignore # can not be None

    @discord.ui.button(label="Stop", emoji="<:stop:1294459644722282577>", style=discord.ButtonStyle.red)
    async def stop_view(self, itn: discord.Interaction, _: discord.ui.Button):
        await itn.response.defer()
        await itn.delete_original_response()
        self.stop()
