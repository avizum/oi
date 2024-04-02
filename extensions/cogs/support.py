from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import core

if TYPE_CHECKING:

    from core import Context, OiBot


RESOLVED = 1019838841005289513
HELP_FORUM = 1019682191749423155
SUPPORT_SERVER = 866891524319084587


class SupportServer(core.Cog, command_attrs=dict(hidden=True)):
    """
    Support Server utilities.
    """

    @core.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        if thread.parent_id != HELP_FORUM:
            return

        message = (
            "Hello, welcome to the support forum. Please provide as much information as possible.\n"
            "Sending screen recordings or screenshots of your issue is greatly appreciated.\n"
            "To close this post, use </close:1223887664726540298>."
        )

        await thread.send(message)

    @staticmethod
    def in_help():
        def predicate(ctx: Context):
            if isinstance(ctx.channel, discord.Thread) and ctx.channel.parent_id == HELP_FORUM:
                return True
            raise commands.CheckFailure("This command can only be used in the help forum.")

        return commands.check(predicate)

    @core.command()
    @app_commands.guilds(SUPPORT_SERVER)
    @in_help()
    async def close(self, ctx: Context):
        """
        Closes and marks a help thread as Resolved.
        """
        assert isinstance(ctx.channel, discord.Thread)
        assert isinstance(ctx.channel.parent, discord.ForumChannel)

        # not using app_commands because they don't have ctx
        if not ctx.interaction:
            return

        resolved = ctx.channel.parent.get_tag(1019838841005289513)
        if not resolved:
            return await ctx.send("Could not find Resolved tag.", ephemeral=True)

        if ctx.author.id == ctx.channel.owner_id or ctx.permissions.manage_threads:
            await ctx.send("Marked post as solved.")
            await ctx.channel.edit(archived=True, locked=True, applied_tags=[resolved])

        else:
            if not ctx.channel.owner:
                return await ctx.send("Could not find OP.", ephemeral=True)
            conf = await ctx.confirm(
                message=f"{ctx.channel.owner.mention}, Mark post as solved?",
                allowed=[ctx.channel.owner],
            )
            if conf.result:
                await conf.message.edit(content="Marked post as solved.")
                await ctx.channel.edit(archived=True, locked=True, applied_tags=[resolved])
            else:
                await conf.message.edit(content="Timed out.")


async def setup(bot: OiBot):
    await bot.add_cog(SupportServer(bot))
