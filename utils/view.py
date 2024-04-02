import discord


class OiView(discord.ui.View):
    def __init__(self, *, members: list[discord.Member | discord.User], timeout: int = 180):
        self.members: list[discord.Member | discord.User] = members
        self.message: discord.Message | None
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in self.members:
            await interaction.response.send_message("This can not be used by you.", ephemeral=True)
            return False
        return True
