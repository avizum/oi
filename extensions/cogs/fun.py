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

import random
import re
from typing import Literal, TYPE_CHECKING

import discord
from discord.ext import menus

import core
from utils.paginators import Paginator

if TYPE_CHECKING:
    from core import Context, OiBot
    from utils.types import UrbanData


class RPSButton(discord.ui.Button["RPSView"]):
    def __init__(self, *, label: str, emoji: str, value: int) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.gray, emoji=emoji)
        self.value: int = value
        self.picker: discord.Member | None = None

    async def callback(self, itn: discord.Interaction) -> None:
        assert self.view is not None
        assert isinstance(itn.user, discord.Member)
        self.picker = itn.user
        return await self.view.answer(itn, self)


class RPSView(discord.ui.View):
    def __init__(self, *, ctx: Context, opponent: discord.Member, embed: discord.Embed) -> None:
        super().__init__(timeout=30)
        self.message: discord.Message
        self.ctx = ctx
        self.opponent = opponent
        self.embed = embed
        self.player_choice: int | None = None
        self.opponent_choice: int | None = None
        self.fill_items()

    def fill_items(self) -> None:
        self.add_item(RPSButton(label="Rock", emoji="\U0001faa8", value=0))
        self.add_item(RPSButton(label="Paper", emoji="\U0001f4f0", value=1))
        self.add_item(RPSButton(label="Scissors", emoji="\U00002702", value=2))

    async def interaction_check(self, itn: discord.Interaction) -> bool:
        return itn.user.id in (self.ctx.author.id, self.opponent.id)

    async def answer(self, itn: discord.Interaction, button: RPSButton) -> None:
        if self.opponent.bot:
            self.opponent_choice = random.choice([0, 1, 2])
        if itn.user.id == self.ctx.author.id:
            if self.player_choice is not None:
                return await itn.response.defer()
            self.player_choice = button.value
        elif itn.user.id == self.opponent.id:
            if self.opponent_choice is not None:
                return await itn.response.defer()
            self.opponent_choice = button.value

        if self.opponent.bot:
            await itn.response.defer()
        else:
            await itn.response.send_message(f"You chose {button.label}.", ephemeral=True)

        if self.player_choice is not None and self.opponent_choice is not None:
            game: dict[int, str] = {0: "Rock", 1: "Paper", 2: "Scissors"}
            key: list[list[int]] = [[-1, 1, 0], [1, -1, 2], [0, 2, -1]]
            responses: dict[int, str] = {
                -1: "It's a tie",
                0: "Rock crushes scissors",
                1: "Paper covers rock",
                2: "Scissors cut paper",
            }
            final_key = key[self.player_choice][self.opponent_choice]
            if final_key == self.player_choice:
                winner = f"**{self.ctx.author.display_name}**"
            elif final_key == self.opponent_choice:
                winner = f"**{self.opponent.display_name}**"
            else:
                winner = "nobody"

            action = responses[final_key]
            self.embed.description = (
                f"**{self.ctx.author.display_name}** chose **{game[self.player_choice]}**.\n"
                f"**{self.opponent.display_name}** chose **{game[self.opponent_choice]}**.\n\n{action}, {winner} wins!"
            )
            for item in self.children:
                if isinstance(item, RPSButton):
                    if item.picker and item.value == final_key:
                        item.style = discord.ButtonStyle.green
                    elif item.picker:
                        item.style = discord.ButtonStyle.red
                        if final_key == -1:
                            item.style = discord.ButtonStyle.blurple
                    item.disabled = True
            await self.message.edit(embed=self.embed, view=self)


class GuessModal(discord.ui.Modal, title="Guess the Number"):
    guess = discord.ui.TextInput(label="Hello.")

    def __init__(self, *, view: GuessView, number: int) -> None:
        super().__init__(timeout=60)
        self.number = number
        self.view = view
        self.guess.label = "Enter your guess! (1-50)"
        self.guess.max_length = 2
        self.guess.min_length = 1
        self.guess.placeholder = f"Maybe it's {random.randint(1, 50)}? Who knows?"

    async def on_submit(self, itn: discord.Interaction, /) -> None:
        try:
            int(self.guess.value)
        except ValueError:
            return await itn.response.send_message("Please enter a number!", ephemeral=True)
        if int(self.guess.value) == self.number:
            await itn.response.send_message("You guessed correctly!", ephemeral=True)
            await self.view.message.edit(
                content=f"{itn.user.display_name} guessed the correct number! It was {self.number}!", view=None
            )
        elif int(self.guess.value) > self.number:
            await itn.response.send_message("Lower, try again!", ephemeral=True)
        elif int(self.guess.value) < self.number:
            await itn.response.send_message("Higher, try again!", ephemeral=True)


class GuessView(discord.ui.View):
    def __init__(self, *, ctx: Context, number: int):
        super().__init__()
        self.ctx: Context = ctx
        self.number = number
        self.message: discord.Message

    @discord.ui.button(label="Guess", style=discord.ButtonStyle.green)
    async def guess(self, itn: discord.Interaction, button: discord.ui.Button) -> None:
        await itn.response.send_modal(GuessModal(view=self, number=self.number))


BRACKETED = re.compile(r"(\[(.+?)\])")


class UrbanSource(menus.ListPageSource):
    def __init__(self, data: list[UrbanData]) -> None:
        super().__init__(data, per_page=1)

    def cleanup_definition(self, definition: str, *, regex: re.Pattern = BRACKETED) -> str:
        def repl(m):
            word = m.group(2)
            return f'[{word}](http://{word.replace(" ", "-")}.urbanup.com)'

        ret = regex.sub(repl, definition)
        if len(ret) >= 1024:
            return f"{ret[:1000]} [...]"
        return ret

    async def format_page(self, menu: menus.MenuPages, entry: UrbanData) -> discord.Embed:
        embed = discord.Embed(
            title=f"{entry['word']}",
            url=entry["permalink"],
            timestamp=discord.utils.parse_time(entry["written_on"]),
            color=0x00FFB3,
        )
        embed.add_field(name="Definition", value=self.cleanup_definition(entry["definition"]), inline=False)
        embed.add_field(name="Example", value=self.cleanup_definition(entry["example"]), inline=False)
        embed.timestamp = discord.utils.parse_time(entry["written_on"])
        embed.set_footer(text=f"👍 {entry['thumbs_up']} 👎 {entry['thumbs_down']} | by {entry['author']}")

        return embed


class Fun(core.Cog):
    """
    Some fun commands and games for very great fun.
    """

    @property
    def display_emoji(self) -> str:
        return "\U0001f3ae"

    @core.group()
    async def games(self, ctx: Context) -> None:
        """
        Games for you and your friends to play.
        """
        await ctx.send_help(ctx.command)

    @games.command()
    @core.has_voted()
    @core.describe(opponent="Who to play against.")
    async def rockpaperscissors(self, ctx: Context, opponent: discord.Member | None = None):
        """
        Play rock paper scissors with someone.
        """
        if opponent and opponent.bot:
            return await ctx.send("You can't play against a bot.")
        elif opponent == ctx.author:
            return await ctx.send("You can't play against yourself.")
        if opponent is None:
            opponent = ctx.me

        if opponent.id is not ctx.me.id:
            response = await ctx.confirm(
                message=(
                    f"{opponent.mention}, would you like to play against "
                    f"{ctx.author.mention} in a game of rock paper scissors?"
                ),
                allowed=[opponent],
                remove_view_after=True,
            )
            if not response.result:
                return await response.message.edit(content=f"{opponent.mention} did not want to play.")

        embed = discord.Embed(
            title="Rock Paper Scissors",
            description=f"**{ctx.author.display_name}** vs **{opponent.display_name}**\n\nWho will win?",
        )
        view = RPSView(ctx=ctx, opponent=opponent, embed=embed)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @games.command()
    async def guess(self, ctx: Context):
        """
        Try to guess the number.
        """
        view = GuessView(ctx=ctx, number=random.randint(1, 50))
        msg = await ctx.send("Guess the number between 1 and 50!", view=view)
        view.message = msg

    @core.group()
    async def fun(self, ctx: Context) -> None:
        """
        Some fun commands.
        """
        await ctx.send_help(ctx.command)

    @fun.command()
    @core.describe(question="The question to ask the magic eight-ball.")
    async def eightball(self, ctx: Context, *, question: str):
        """
        Ask the magic eight-ball a question.
        """
        responses = [
            "It is certain",
            "Without a doubt",
            "You may rely on it",
            "Yes definitely",
            "It is decidedly so",
            "As I see it, yes",
            "Most likely",
            "Yes",
            "Outlook good",
            "Signs point to yes",
            "Reply hazy try again",
            "Better not tell you now",
            "Ask again later",
            "Cannot predict now",
            "Concentrate and ask again",
            "Don't count on it",
            "Outlook not so good",
            "My sources say no",
            "Very doubtful",
            "No",
        ]
        embed = discord.Embed(
            title="Magic 8 ball",
            description=f"> {question}\n{random.choice(responses)}",
        )
        await ctx.send(embed=embed)

    @fun.command()
    async def coinflip(self, ctx: Context):
        """
        Flip a coin.
        """
        await ctx.send(random.choice(["I got heads!", "I got tails!"]))

    @fun.command()
    @core.describe(type="The type of dice to roll.")
    async def roll(self, ctx: Context, type: Literal["D4", "D6", "D8", "D10", "D12", "D20"] = "D6"):
        """
        Roll a dice.
        """
        await ctx.send(f"{type}: a {random.randint(1, int(type[1:]))} was rolled")

    @fun.command()
    @core.has_voted()
    @core.describe(query="The query to search the Urban Dictionary for.")
    async def urban(self, ctx: Context, *, query: str):
        """
        Search the Urban Dictionary.
        """
        response = await self.bot.session.get("http://api.urbandictionary.com/v0/define", params={"term": query})
        if response.status != 200:
            return await ctx.send(f"An error occured: [{response.status}] {response.reason}")
        data = await response.json()
        if not data["list"]:
            return await ctx.send("No results found mathing your query.")

        paginator = Paginator(UrbanSource(data["list"]), ctx=ctx, remove_view_after=True)
        await paginator.start()

    @fun.command()
    @core.describe(text="The text to repeat.")
    async def echo(self, ctx: Context, *, text: str):
        """
        Repeat some text.
        """
        await ctx.send(text)

    @core.group()
    async def random(self, ctx: Context):
        """
        Some random stuff.
        """
        await ctx.send_help(ctx.command)

    @random.command()
    async def uselessfact(self, ctx: Context):
        """
        Get a random fact.
        """
        async with ctx.typing():
            resp = await self.bot.session.get("https://uselessfacts.jsph.pl/random.json?language=en")
            json = await resp.json()
            await ctx.send(json["text"])

    @random.command()
    async def dogfact(self, ctx: Context):
        """
        Get a random fact about dogs.
        """
        async with ctx.typing():
            resp = await self.bot.session.get("https://dogapi.dog/api/v2/facts")
            json = await resp.json()
            fact = json["data"][0]["attributes"]["body"]
            await ctx.send(fact)

    @random.command()
    async def catfact(self, ctx: Context):
        """
        Get a random fact about cats.
        """
        async with ctx.typing():
            resp = await self.bot.session.get("https://catfact.ninja/fact")
            json = await resp.json()
            fact = json["fact"]
            await ctx.send(fact)

    @random.command()
    async def activity(self, ctx: Context, safe: bool = True):
        """
        Get a random activity.
        """
        async with ctx.typing():
            resp = await self.bot.session.get("https://bored-api.appbrewery.com/random")
            json = await resp.json()
            await ctx.send(json["activity"])


async def setup(bot: OiBot) -> None:
    await bot.add_cog(Fun(bot))
