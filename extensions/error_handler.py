from __future__ import annotations

import contextlib
import io
import logging
import traceback
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import core
from utils.exceptions import Maintenance, NotVoted

if TYPE_CHECKING:
    from core import Context, OiBot

_log = logging.getLogger("oi.commands")

VOTE_VIEW = discord.ui.View()
VOTE_VIEW.add_item(
    discord.ui.Button(
        label="Vote on top.gg",
        emoji="<:topgg:1058957715491274772>",
        url="https://top.gg/bot/867713143366746142/vote",
    )
)


class ErrorHandler(core.Cog):
    def __init__(self, bot: OiBot):
        self.bot = bot
        self.webhook = discord.Webhook.from_url(
            bot.config["ERROR_WEBHOOK"],
            session=self.bot.session,
        )
        self._original_tree_error = self.bot.tree.on_error
        self.bot.tree.on_error = self.on_tree_error

    async def cog_unload(self) -> None:
        self.bot.tree.on_error = self._original_tree_error

    async def on_tree_error(self, itn: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandNotFound):
            return await itn.response.send_message("This command is unavailable right now.", ephemeral=True)
        else:
            _log.error(f"Ignoring exception in tree command {itn.command}:", exc_info=error)

    @core.Cog.listener()
    async def on_command_error(self, ctx: Context, exc: commands.CommandError):
        error = getattr(exc, "original", exc)

        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original

        if isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, NotVoted):
            return await ctx.send("You need to vote for Oi to use this command.", ephemeral=True, view=VOTE_VIEW)

        elif isinstance(error, Maintenance):
            return await ctx.send("Oi is currently under maintenance.", ephemeral=True)

        elif isinstance(error, discord.NotFound) and error.code == 10062:
            return

        elif isinstance(error, discord.Forbidden) and error.code == 50013:
            with contextlib.suppress(discord.Forbidden):
                return await ctx.send("I am missing permissions to do this.", ephemeral=True)
            return

        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            return await ctx.send(f'Could not find member "{error.argument}".', ephemeral=True)

        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"You are on cooldown. Try again after {error.retry_after:.2f} seconds.", ephemeral=True)

        elif isinstance(error, commands.MaxConcurrencyReached):
            return await ctx.send(f"Please wait. This command is limited to {error.number} concurrent uses.", ephemeral=True)

        elif isinstance(error, commands.BadArgument):
            return await ctx.send(f"Invalid argument: {error}", ephemeral=True)

        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"Missing argument: {error.param.name}", ephemeral=True)

        elif isinstance(error, commands.UserInputError):
            return await ctx.send(f"Invalid input: {error}", ephemeral=True)

        elif isinstance(error, commands.NotOwner):
            return await ctx.send("You can not run this command.", ephemeral=True)

        elif isinstance(error, commands.MissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in error.missing_permissions]
            return await ctx.send(f"You are missing the following permissions:\n{', '.join(missing)}", ephemeral=True)

        elif isinstance(error, commands.BotMissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in error.missing_permissions]
            return await ctx.send(f"I am missing the following permissions:\n{', '.join(missing)}", ephemeral=True)

        elif isinstance(error, commands.CheckFailure):
            return await ctx.send(str(error), ephemeral=True)

        elif isinstance(error, commands.DisabledCommand):
            return await ctx.send("This command is disabled.", ephemeral=True)

        else:
            embed = discord.Embed(
                title="An error occurred :(", description=f"```py\n{error}\n```", color=discord.Color.red()
            )
            embed.set_footer(text="Error has been logged and will be addressed soon.")
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/hWhGQ4QHE9"))
            await ctx.send(embed=embed, view=view, ephemeral=True)

            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))

            if ctx.interaction:
                ns = ctx.interaction.namespace
                params = [f"{i[0]}: {i[1]}" for i in ns]
                message = f"/{ctx.command.qualified_name} {' '.join(params)}"
            else:
                message = ctx.message.content.replace(f"<@{self.bot.user.id}>", f"@{self.bot.user.name}")
            dev_embed = discord.Embed(
                title="An error occurred :(",
                description=(
                    f"**Command:** {ctx.command}\n"
                    f"**Message:** `{message}` | `{ctx.message.id}`\n\n"
                    f"**Channel:** {ctx.channel} | `{ctx.channel.id}`\n"
                    f"**User:** {ctx.author} | `{ctx.author.id}`\n"
                    f"**Guild:** {ctx.guild} | `{ctx.guild.id}`"
                ),
            )
            if len(tb) > 1995:
                error_file = discord.File(fp=io.BytesIO(tb.encode("utf-8")), filename=f"error_{ctx.command}.txt")
                await self.webhook.send(file=error_file, embed=dev_embed)
            else:
                await self.webhook.send(embed=dev_embed, content=f"```py\n{tb}\n```")

            _log.error(f"Ignoring exception in command {ctx.command}:", exc_info=error)


async def setup(bot: OiBot):
    await bot.add_cog(ErrorHandler(bot))
