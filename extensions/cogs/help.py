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

from typing import Any, Mapping, TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, menus
from discord.ext.commands.hybrid import _CallableDefault

import core
from utils import Paginator

if TYPE_CHECKING:
    from discord.ext.commands.hybrid import HybridAppCommand

    from core import Context, OiBot

COLOR = 0x00FFB3


class CommandParameter:
    def __init__(self, *, name: str, description: str, default: Any, required: bool, greedy: bool) -> None:
        self.name = name
        self.description = description
        self.default = default
        self.required = required
        self.greedy = greedy

    @property
    def signature(self) -> str:
        result = []
        if self.required and not self.greedy:
            result.append(f"<{self.name}> —")
        elif self.greedy:
            result.append(f"[{self.name}...] —")
        else:
            result.append(f"[{self.name}] —")
        result.append(self.description)
        if self.default is not None and not self.required:
            result.append(f"(Default: {self.default})")
        return " ".join(result)


class Home(menus.PageSource):
    def __init__(self, ctx: Context, help: OiHelp) -> None:
        self.ctx: Context = ctx
        self.help: OiHelp = help
        super().__init__()

    def is_paginating(self) -> bool:
        return True

    def get_max_pages(self) -> int:
        return 2

    async def get_page(self, page_number: int) -> Home:
        self.index = page_number
        return self

    async def format_page(self, menu: menus.Menu, page: Any) -> discord.Embed:
        ctx = self.ctx
        embed = discord.Embed(
            title="Help Menu",
            color=COLOR,
        )

        if self.index == 0:
            commands = list(ctx.bot.walk_commands())
            can_use = await self.help.filter_commands(commands)
            embed.description = (
                f"Hello, {ctx.author.name}!\n"
                "I am a multi-purpose bot, packed with a lot of features.\n"
                f"There are {len(commands)} commands, and {len(can_use)} commands you can use."
            )
            embed.add_field(name="Bot News", value=f"{ctx.bot.news}", inline=False)
            embed.set_footer(text="Use the dropdown menu to select a module.")

        elif self.index == 1:
            embed.description = "Need help using the help command?"
            embed.add_field(
                name="Command usage",
                value=(
                    "Reading command signatures is easy.\n"
                    "Example: `/command <parameter_one> [parameter_two]`\n"
                    "When using the command, replace the parameters with your own values.\n"
                    "With slash commands, your Discord client will help you a lot."
                ),
                inline=False,
            )
            embed.add_field(
                name="Command parameters",
                value=(
                    "Parameters are the values you need to provide to the command. "
                    "Some commands have parameters, while others don't.\n"
                    "`<parameter>` - is a required parameter.\n"
                    "`[parameter]` - is an optional parameter, there may be a default value.\n"
                    "`[parameter...]` - is a variadic parameter, you can provide multiple values."
                ),
            )

        return embed


class CogHelpPages(menus.ListPageSource):
    def __init__(self, help: OiHelp, cog: core.Cog):
        self.help: OiHelp = help
        self.cog: core.Cog = cog
        commands = cog.get_commands()
        super().__init__(commands, per_page=5)

    async def format_page(self, menu: menus.Menu, commands: list[core.HybridCommand]) -> discord.Embed:
        cog = self.cog
        embed = discord.Embed(
            title=f"{cog.qualified_name} Commands",
            description=cog.description or "No description provided.",
            color=COLOR,
        )
        embed.add_field(
            name=f"Commands in {cog.qualified_name}",
            value="\n".join(f"{command.name} - {command.short_doc or 'No help provided.'}" for command in commands),
            inline=False,
        )
        embed.set_footer(text="Use the dropdown menus to select a command or module.")
        return embed

    async def get_page(self, page_number: int) -> list[core.HybridCommand]:
        base = page_number * self.per_page
        return list(self.entries[base : base + self.per_page])


class GroupHelpPages(menus.ListPageSource):
    def __init__(self, help: OiHelp, group: core.HybridGroup):
        self.help: OiHelp = help
        self.group: core.HybridGroup = group
        commands = []
        if isinstance(self.group, core.HybridGroup) and self.group.fallback:
            # If the group has a fallback, it means the group command has functionality, so we need to display a help page
            # with `create_command_help_embed`. Without a fallback, the base group command only serves to hold
            # subcommands and has no other functionality besides showing a help message for the group.
            # To easily show a "front page" for the group command, we just append numbers and check for it in `format_page`.
            commands.extend([1, 2, 3, 4, 5])
        commands.extend(group.commands)
        super().__init__(commands, per_page=5)

    async def format_page(self, menu: menus.Menu, group_commands: list[core.HybridGroup]) -> discord.Embed:
        if isinstance(group_commands[0], int):
            return self.help.create_command_help_embed(self.group)
        embed = discord.Embed(
            title=f"Command Group: {self.group.qualified_name}",
            description=self.group.help or "No description provided.",
            color=COLOR,
        )

        member_perms, bot_perms = self.help.get_command_permissions(self.group)
        embed.add_field(name="Required Permissions", value=f"{member_perms}\n{bot_perms}", inline=False)

        embed.add_field(
            name="Commands in group",
            value="\n".join(f"{command.name} - {command.short_doc or 'No help provided.'}" for command in group_commands),
            inline=False,
        )

        return embed

    async def get_page(self, page_number: int) -> list[core.HybridCommand]:
        base = page_number * self.per_page
        return list(self.entries[base : base + self.per_page])


class CogSelect(discord.ui.Select["HelpPaginator"]):
    def __init__(self, help: OiHelp, cogs: list[core.Cog]) -> None:
        self.help: OiHelp = help
        self.cogs: list[core.Cog] = cogs
        options = [
            discord.SelectOption(label="Home", description="Home page of the help menu.", emoji="🏠"),
        ]
        options.extend(
            discord.SelectOption(
                label=cog.qualified_name,
                description=cog.description,
                emoji=cog.display_emoji,
            )
            for cog in cogs
        )
        super().__init__(
            options=options,
            placeholder="Select a module...",
            min_values=1,
            max_values=1,
        )

    async def callback(self, itn: discord.Interaction) -> None:
        assert self.view is not None
        if self.values[0] == "Home":
            for i in self.view.children:
                if isinstance(i, CommandSelect):
                    self.view.remove_item(i)
            await self.view.switch(Home(self.help.context, self.help), itn)
            return

        cog: core.Cog | None = self.help.context.bot.get_cog(self.values[0])  # type: ignore

        if cog is None:
            await itn.response.send_message("This module is unavailable.", ephemeral=True)
            return

        menu = CogHelpPages(self.help, cog)
        commands = await menu.get_page(0)
        self.view.add_item(CommandSelect(self.help, commands))
        await self.view.switch(menu, itn)
        return


class CommandSelect(discord.ui.Select["HelpPaginator"]):
    def __init__(self, help: OiHelp, commands: list[core.HybridCommand]) -> None:
        self.help: OiHelp = help
        self.commands: list[core.HybridCommand] = commands
        self.dummy: discord.SelectOption = discord.SelectOption(label="Command", value="Command")
        disabled: bool = False

        if isinstance(commands[0], int):
            options = [self.dummy]
            disabled = True
        else:
            options = [
                discord.SelectOption(label=command.qualified_name, description=command.short_doc or "No help provided.")
                for command in commands
            ]
        super().__init__(options=options, placeholder="Select a command...", min_values=1, max_values=1, disabled=disabled)

    def _update(self, commands: list[core.HybridCommand]) -> None:
        self.options.clear()
        self.disabled = False
        if isinstance(commands[0], int):
            self.options.append(self.dummy)
            self.disabled = True
            return
        for command in commands:
            self.options.append(
                discord.SelectOption(label=command.qualified_name, description=command.short_doc or "No help provided.")
            )

    async def callback(self, itn: discord.Interaction) -> None:
        assert self.view is not None
        command: core.HybridCommand | None = self.help.context.bot.get_command(self.values[0])  # type: ignore
        self.selected = command
        if command is None:
            await itn.response.send_message("This command is unavailable.", ephemeral=True)
            return None
        if isinstance(command, core.HybridGroup):
            menu = GroupHelpPages(self.help, command)
            commands = await menu.get_page(0)
            self.view.add_item(CommandSelect(self.help, commands))
            return await self.view.switch(menu, itn)
        embed = self.help.create_command_help_embed(command)
        previous = itn.message or self.view.message
        previous_embed = previous.embeds[0]
        await self.view.message.edit(
            embed=embed, view=CommandHelpView(self.view.timeout, self.help, self.view, previous_embed=previous_embed)
        )
        return None


class CommandHelpView(discord.ui.View):
    def __init__(self, timeout: float | None, help: OiHelp, help_view: HelpPaginator, previous_embed: discord.Embed) -> None:
        super().__init__(timeout=timeout)
        self.help: OiHelp = help
        self.help_view: HelpPaginator = help_view
        self.previous_embed: discord.Embed = previous_embed

    async def interaction_check(self, itn: discord.Interaction, /) -> bool:
        if itn.user.id != self.help.context.author.id:
            await itn.response.send_message("You can not use this menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="<:left:1294459831733719100>", label="Back", style=discord.ButtonStyle.secondary)
    async def back(self, itn: discord.Interaction, button: discord.ui.Button) -> None:
        if self.help_view.started:
            await itn.response.edit_message(view=self.help_view, embed=self.previous_embed)
        else:
            await self.help_view.start(itn)
        self.stop()


class HelpPaginator(Paginator):
    def __init__(
        self,
        source: menus.PageSource,
        *,
        ctx: Context,
        cogs: list[core.Cog],
        help: OiHelp,
        message: discord.Message | None = None,
    ) -> None:
        super().__init__(source, ctx=ctx, timeout=120.0, check_embeds=True, delete_message_after=True, message=message)
        self.help: OiHelp = help
        self.cogs: list[core.Cog] = cogs
        self.started: bool = False

    async def _update(self, index: int) -> None:
        for i in self.children:
            if isinstance(i, CommandSelect):
                assert i.view is not None
                cmds = await i.view.source.get_page(index)
                i._update(cmds)
        await super()._update(index)

    async def switch(self, source: menus.PageSource, itn: discord.Interaction) -> None:
        self.source = source
        self.current_page = 0
        cog_select = None
        command_select = None
        for i in self.children:
            if isinstance(i, CogSelect):
                cog_select = i
            elif isinstance(i, CommandSelect):
                command_select = i
        self.clear_items()
        if cog_select is not None:
            self.add_item(cog_select)
        if command_select is not None:
            self.add_item(command_select)
        self._fill_items()
        await self.source._prepare_once()
        page = await self.source.get_page(0)
        kwargs = await self._get_kwargs(page)
        await self._update(0)
        await itn.response.edit_message(**kwargs, view=self)

    async def _prepare(self) -> None:
        self.clear_items()
        self.add_item(CogSelect(self.help, self.cogs))
        commands = await self.source.get_page(0)
        self.add_item(CommandSelect(self.help, commands))
        self._fill_items()

    async def start(
        self, entity: discord.Interaction | discord.Message | None = None, prepare: bool = True
    ) -> discord.Message:
        if prepare:
            await self._prepare()
        await self.source._prepare_once()
        page = await self.source.get_page(self.current_page)
        kwargs = await self._get_kwargs(page)
        await self._update(self.current_page)
        if isinstance(entity, discord.Message):
            self.message = entity
            await entity.edit(**kwargs, view=self)
        elif isinstance(entity, discord.Interaction):
            assert entity.message is not None
            self.message = entity.message
            await entity.response.edit_message(**kwargs, view=self)
        else:
            self.message: discord.Message = await self.ctx.send(**kwargs, view=self)
        self.started = True
        return self.message


class OiHelp(commands.HelpCommand):
    context: Context

    def get_parameter_info(
        self, entity: core.HybridCommand[Any, ..., Any] | core.HybridGroup[Any, ..., Any], /
    ) -> list[CommandParameter] | None:
        if not getattr(entity, "__commands_is_hybrid__", None):
            return None

        app_command: HybridAppCommand | app_commands.Group | None = getattr(entity, "app_command", None)
        if app_command is None:
            return None
        info = []

        if isinstance(app_command, app_commands.Group):
            assert isinstance(entity, core.HybridGroup)
            command: app_commands.Command | None = app_command.get_command(entity.fallback or "")  # type: ignore
            if not command:
                return None
        else:
            command = app_command

        for param in command.parameters:
            text_cmd = entity.clean_params[param.name].converter
            greedy = isinstance(text_cmd, commands.Greedy)
            if isinstance(param.default, _CallableDefault):
                default = entity.params[param.name].displayed_default or None
            else:
                default = param.default

            description = "No description provieded" if param.description == "…" else param.description
            info.append(
                CommandParameter(
                    name=param.name, description=description, default=default, required=param.required, greedy=greedy
                )
            )

        return info

    def get_command_permissions(self, command: core.HybridCommand | core.HybridGroup, /) -> tuple[str, str]:
        member_permissions = getattr(command, "member_permissions", None) or getattr(
            command, "member_guild_permissions", None
        )
        bot_permissions = getattr(command, "bot_permissions", None) or getattr(command, "bot_guild_permissions", None)

        can_run = "Can run: <:green_tick:1294459924218384384>"
        member_missing = []
        if member_permissions:
            member_perms = self.context.permissions if command.member_permissions else self.context.guild_permissions
            member_missing = [perm for perm in member_permissions if not getattr(member_perms, perm, False)]
        if member_missing:
            can_run = "Can run: <:red_tick:1294459715266547742>"

        bot_can_run = "Can run: <:green_tick:1294459924218384384>"
        bot_missing = []
        if bot_permissions:
            bot_perms = self.context.bot_permissions if command.bot_permissions else self.context.bot_guild_permissions
            bot_missing = [perm for perm in bot_permissions if not getattr(bot_perms, perm, False)]

        if bot_missing:
            bot_can_run = "Can run: <:red_tick:1294459715266547742>"

        fmt_member = (
            ", ".join(member_permissions).replace("_", " ").replace("guild", "server").title()
            if member_permissions
            else "Nothing"
        )

        fmt_bot = (
            ", ".join(bot_permissions).replace("_", " ").replace("guild", "server").title() if bot_permissions else "Nothing"
        )

        final_member = f"You need: `{fmt_member}` | {can_run}"
        final_bot = f"I need: `{fmt_bot}` | {bot_can_run}"

        return final_member, final_bot

    def create_command_help_embed(self, command: core.HybridCommand | core.HybridGroup, /) -> discord.Embed:
        command_or_group = "Command" if isinstance(command, core.HybridCommand) else "Command Group"
        embed = discord.Embed(
            title=f"{command_or_group}: {command.qualified_name}",
            description=command.help or "No command description provided.",
            color=COLOR,
        )

        value = f"`@{self.context.me.display_name} {command.qualified_name} {command.signature}`"
        if isinstance(command, core.HybridGroup):
            usage = f"`/{command.qualified_name} {command.fallback} {command.signature}`"
            value = usage if self.context.interaction else f"{usage}\n{value}"
        else:
            usage = f"`/{command.qualified_name} {command.signature}`"
            value = usage if self.context.interaction else f"{usage}\n{value}"

        embed.add_field(name="Usage", value=value, inline=False)

        params = self.get_parameter_info(command)
        if params:
            itms = [item.signature for item in params]
            embed.add_field(name="Parameters", value="\n".join(itms), inline=False)

        member_perms, bot_perms = self.get_command_permissions(command)

        embed.add_field(name="Required Permissions", value=f"{member_perms}\n{bot_perms}", inline=False)

        return embed

    async def filter_cogs(
        self, mapping: Mapping[core.Cog | None, list[core.HybridCommand[Any, (...), Any]]] | None = None, /
    ) -> list[core.Cog]:
        cogs = []
        new_mapping = mapping or self.get_bot_mapping()
        for cog, cmds in new_mapping.items():
            if cog is None:
                continue
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                cogs.append(cog)
        cogs.sort(key=lambda c: c.qualified_name)
        return cogs

    async def send_error_message(self, error: str, /) -> None:
        await self.context.send(error, ephemeral=True)

    async def send_bot_help(self, mapping: Mapping[core.Cog | None, list[core.HybridCommand[Any, (...), Any]]], /) -> None:
        cogs = await self.filter_cogs(mapping)
        menu = Home(self.context, self)
        paginator = HelpPaginator(menu, ctx=self.context, cogs=cogs, help=self)
        paginator.clear_items()
        paginator.add_item(CogSelect(self, cogs))
        paginator._fill_items()
        await paginator.start(prepare=False)

    async def send_cog_help(self, cog: core.Cog, /) -> None:
        menu = CogHelpPages(self, cog)
        cogs = await self.filter_cogs()
        paginator = HelpPaginator(menu, ctx=self.context, cogs=cogs, help=self)
        await paginator.start()

    async def send_group_help(self, group: core.HybridGroup, /) -> None:
        menu = GroupHelpPages(self, group)
        cogs = await self.filter_cogs()
        paginator = HelpPaginator(menu, ctx=self.context, cogs=cogs, help=self)
        await paginator.start()

    async def send_command_help(self, command: core.HybridCommand, /) -> None:
        menu = CogHelpPages(self, command.cog)
        cogs = await self.filter_cogs()
        paginator = HelpPaginator(menu, ctx=self.context, cogs=cogs, help=self)
        command_view = CommandHelpView(
            paginator.timeout, self, paginator, await menu.format_page(menu, await menu.get_page(0))  # type: ignore
        )
        await self.context.send(embed=self.create_command_help_embed(command), view=command_view)


class HelpCommandCog(core.Cog):
    def __init__(self, bot: OiBot) -> None:
        self.default = bot.help_command
        bot.help_command = OiHelp(command_attrs={"hidden": True}, verify_checks=False)
        bot.help_command.cog = self
        self.autocomplete_options: list[app_commands.Choice[str]] = []
        super().__init__(bot)

    def cog_unload(self) -> None:
        self.bot.help_command = self.default

    @app_commands.command(name="help")
    @app_commands.guild_only()
    @core.describe(entity="What you need help with.")
    async def _help(self, itn: discord.Interaction, entity: str | None = None):
        """Shows help for commands or modules."""
        ctx = await self.bot.get_context(itn)
        # This is the only app_commands.command, so in order for this command to be logged, we do this:
        command = self.bot.get_command("help")
        if command is None:
            # command should never be none, If this cog is unloaded, then help is none,
            # and this command wouldn't be invoked in the first place.
            return None
        ctx.command = command
        self.bot.dispatch("command", ctx)

        if entity is not None:
            cmd = self.bot.get_command(entity) or self.bot.get_cog(entity)
            if cmd is None:
                return await ctx.send("Command not found.", ephemeral=True)
            return await ctx.send_help(cmd)
        return await ctx.send_help()

    @_help.autocomplete("entity")
    async def _help_autocomplete(
        self,
        _: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not self.autocomplete_options:
            for cmd in self.bot.walk_commands():
                if cmd.hidden:
                    continue
                if isinstance(cmd, core.HybridGroup) and cmd.fallback:
                    self.autocomplete_options.append(
                        app_commands.Choice(name=f"{cmd.qualified_name} {cmd.fallback}", value=cmd.qualified_name)
                    )
                else:
                    self.autocomplete_options.append(app_commands.Choice(name=cmd.qualified_name, value=cmd.qualified_name))
            self.autocomplete_options.extend(
                app_commands.Choice(name=cog.qualified_name, value=cog.qualified_name) for cog in self.bot.cogs.values()
            )

        return [choice for choice in self.autocomplete_options if current in choice.name][:25]


async def setup(bot: OiBot) -> None:
    await bot.add_cog(HelpCommandCog(bot))
