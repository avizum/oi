from core import OiBot

from .cog import Music


async def setup(bot: OiBot) -> None:
    await bot.add_cog(Music(bot))
