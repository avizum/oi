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

import logging
from typing import TYPE_CHECKING

from discord import Webhook
from discord.ext import tasks
from discord.ext.commands import Paginator

import core

if TYPE_CHECKING:
    from core import OiBot


class WebhookHandler(logging.Handler):
    def __init__(self, bot: OiBot, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self.batch: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.batch.append(self.format(record))
        except Exception:
            self.handleError(record)


class WebhookLogger(core.Cog):
    def __init__(self, bot: OiBot) -> None:
        self.handler: WebhookHandler = bot.webhook_handler
        self.webhook = Webhook.from_url(bot.config["LOG_WEBHOOK"], client=bot)
        super().__init__(bot)

    async def cog_load(self) -> None:
        await self.bot.wait_until_ready()
        self.batch_send.start()

    def cog_unload(self) -> None:
        self.batch_send.stop()

    @tasks.loop(seconds=10.0)
    async def batch_send(self):
        batch = self.handler.batch
        if not batch:
            return
        paginator = Paginator(prefix="```ansi", suffix="```")

        for message in batch:
            lines = message.splitlines()
            for line in lines:
                if len(line) >= 1988:
                    line = f"{line[:1985]}..."
                paginator.add_line(line)

        for page in paginator.pages:
            await self.webhook.send(page)

        batch.clear()


async def setup(bot: OiBot) -> None:
    await bot.add_cog(WebhookLogger(bot))
