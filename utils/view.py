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

import discord


class OiView(discord.ui.View):
    def __init__(self, *, members: list[discord.Member | discord.User], timeout: int = 180):
        self.members: list[discord.Member | discord.User] = members
        self.message: discord.Message | None = None
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in self.members:
            await interaction.response.send_message("This can not be used by you.", ephemeral=True)
            return False
        return True
