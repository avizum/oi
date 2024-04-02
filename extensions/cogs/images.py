from __future__ import annotations

import random
from io import BytesIO
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, menus

import core
from utils.paginators import Paginator

if TYPE_CHECKING:
    from waifuim import Image as WaifuImage

    from core import Context, OiBot


SFW_TAGS: list[app_commands.Choice] = [
    app_commands.Choice(name="maid", value="MAID"),
    app_commands.Choice(name="waifu", value="WAIFU"),
    app_commands.Choice(name="marin-kitagawa", value="MARIN-KITAGAWA"),
    app_commands.Choice(name="mori-calliope", value="MORI-CALLIOPE"),
    app_commands.Choice(name="raiden-shogun", value="RAIDEN-SHOGUN"),
    app_commands.Choice(name="oppai", value="OPPAI"),
    app_commands.Choice(name="selfies", value="SELFIES"),
    app_commands.Choice(name="uniform", value="UNIFORM"),
]

NSFW_TAGS: list[app_commands.Choice] = [
    app_commands.Choice(name="ass", value="ASS"),
    app_commands.Choice(name="hentai", value="HENTAI"),
    app_commands.Choice(name="milf", value="MILF"),
    app_commands.Choice(name="oral", value="ORAL"),
    app_commands.Choice(name="paizuri", value="PAIZURI"),
    app_commands.Choice(name="ecchi", value="ECCHI"),
]


class WaifuPaginator(menus.ListPageSource):
    def __init__(self, images: list[WaifuImage], search: str):
        self.search = search
        super().__init__(images, per_page=1)

    async def format_page(self, menu: menus.Menu, image: WaifuImage):
        try:
            color = discord.Color.from_str(image.dominant_color)
        except ValueError:
            color = discord.Color.blurple()
        embed = discord.Embed(title=self.search.title(), color=color)
        embed.set_image(url=image.url)
        embed.set_footer(text="Powered by waifu.im")

        return embed


class Image(core.Cog):
    """
    Image commands.
    """

    @property
    def display_emoji(self) -> str:
        return "\U0001f5bc\U0000fe0f"

    async def get_animal(self, animal: str) -> discord.File:
        resp = await self.bot.session.get(f"https://some-random-api.com/animal/{animal}")
        img = await resp.json()
        return discord.File(
            BytesIO(await (await self.bot.session.get(img["image"])).read()),
            filename=f"{animal}.png",
        )

    async def get_animu(self, animu: str) -> discord.File:
        async with self.bot.session.get(f"https://some-random-api.com/animu/{animu}") as resp:
            json = await resp.json()
            return json["link"]

    async def get_tenor(self, query: str) -> str:
        async with self.bot.session.get(
            f"https://g.tenor.com/v1/search?q={query}&key={self.bot.config['TENOR_API_TOKEN']}&limit=50"
        ) as resp:
            json = await resp.json()
            return random.choice(json["results"])["media"][0]["gif"]["url"]

    @core.group()
    async def images(self, ctx: Context):
        """
        Some image commands.
        """
        await ctx.send_help(ctx.command)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to slap.")
    async def slap(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Slaps someone. Very violent, be careful.

        Images from https://tenor.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} slaps {member.name}!")
            img = await self.get_tenor("anime-slap")
            embed.set_image(url=img)
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to poke.")
    async def poke(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Poke someone. Be careful, may poke eyes out.

        Images from https://tenor.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} pokes {member.name}!")
            img = await self.get_tenor("anime-poke")
            embed.set_image(url=img)
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to bonk.")
    async def bonk(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Bonk someone. Can hurt someone, don't bonk with force!

        Images from https://tenor.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} bonks {member.name}!")
            img = await self.get_tenor("anime-bonk")
            embed.set_image(url=img)
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to kiss (ooooh!)")
    async def kiss(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Kiss someone. NICE!

        Images from https://tenor.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} bonks {member.name}!")
            img = await self.get_tenor("anime-kiss")
            embed.set_image(url=img)
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to bully.")
    async def bully(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Bully someone. Can hurt somone's feelings. Use with care.

        Images from https://tenor.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} bully {member.name}!")
            img = await self.get_tenor("anime-bully")
            embed.set_image(url=img)
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def facepalm(self, ctx: Context):
        """
        Smh my head.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Face Palm")
            embed.set_image(url=await self.get_animu("face-palm"))
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to hug.")
    async def hug(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Hug someone. Very nice.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} hugs {member.name}!")
            embed.set_image(url=await self.get_animu(ctx.command.name))
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to pat.")
    async def pat(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Pat someone.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} pats {member.name}")
            embed.set_image(url=await self.get_animu(ctx.command.name))
            await ctx.send(embed=embed)

    @images.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(member="The person to wink at ;)")
    async def wink(self, ctx: Context, member: discord.Member = commands.Author):
        """
        Wink at someone.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title=f"{ctx.author.name} winks at {member.name}")
            embed.set_image(url=await self.get_animu(ctx.command.name))
            await ctx.send(embed=embed)

    @images.command()
    @core.describe(code="The http code to get an image of like: 404, 403, 200.")
    async def httpcat(self, ctx: Context, code: commands.Range[int, 100, 599]):
        """
        Get an image from https://http.cat
        """
        async with ctx.typing():
            s = await self.bot.session.get(f"https://http.cat/{code}")
            if s.status != 200:
                return await ctx.send("Invalid code.")
            embed = discord.Embed()
            embed.set_image(url=f"https://http.cat/{code}")
            await ctx.send(embed=embed)

    @images.group()
    async def animals(self, ctx: Context):
        """
        Get some images of aniamls.

        Images are from https://some-random-api.com
        """
        await ctx.send_help(ctx.command)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def bird(self, ctx: Context):
        """
        Send a random image of a bird.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Bird")
            embed.set_image(url="attachment://bird.png")
            bird = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=bird)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def cat(self, ctx: Context):
        """
        Send a random image of a cat.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Cat")
            embed.set_image(url="attachment://cat.png")
            cat = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=cat)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dog(self, ctx: Context):
        """
        Send a random image of a dog.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Dog")
            embed.set_image(url="attachment://dog.png")
            dog = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=dog)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def fox(self, ctx: Context):
        """
        Send a random image of a fox.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Fox")
            embed.set_image(url="attachment://fox.png")
            fox = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=fox)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def kangaroo(self, ctx: Context):
        """
        Send a random image of a kangaroo.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Kangaroo")
            embed.set_image(url="attachment://kangaroo.png")
            kangaroo = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=kangaroo)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def koala(self, ctx: Context):
        """
        Send a random image of a koala.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Koala")
            embed.set_image(url="attachment://koala.png")
            koala = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=koala)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def panda(self, ctx: Context):
        """
        Send a random image of a panda.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Panda")
            embed.set_image(url="attachment://panda.png")
            panda = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=panda)

    @animals.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def raccoon(self, ctx: Context):
        """
        Send a random image of a raccoon.

        Images are from https://some-random-api.com
        """
        async with ctx.typing():
            embed = discord.Embed(title="Raccoon")
            embed.set_image(url="attachment://raccoon.png")
            racoon = await self.get_animal(ctx.command.name)
            await ctx.send(embed=embed, file=racoon)

    @core.group()
    async def waifu(self, ctx: Context):
        """
        Get images of waifus.

        Images are from https://waifu.im
        """
        await ctx.send_help(ctx.command)

    @waifu.command(name="sfw")
    @app_commands.choices(tag=SFW_TAGS)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(tag="Type to image to search for.")
    async def waifu_sfw(self, ctx: Context, tag: app_commands.Choice[str]):
        """
        Get images of waifus.

        Images are from https://waifu.im
        """
        search = await self.bot.waifuim.search(included_tags=[tag.value], nsfw=False, multiple=True)
        paginator = Paginator(WaifuPaginator(search, tag.name), ctx=ctx, remove_view_after=True)
        await paginator.start()

    @waifu.command(name="nsfw")
    @commands.is_nsfw()
    @app_commands.choices(tag=NSFW_TAGS)
    @commands.cooldown(1, 5, commands.BucketType.user)
    @core.describe(tag="Type to image to search for.")
    async def waifu_nsfw(self, ctx: Context, tag: app_commands.Choice[str]):
        """
        Get some NSFW images of waifus.

        This command only works in NSFW channels.
        Images are from https://waifu.im
        """
        search = await self.bot.waifuim.search(included_tags=[tag.value], nsfw=True, multiple=True)
        paginator = Paginator(WaifuPaginator(search, tag.name), ctx=ctx, remove_view_after=True)
        await paginator.start()


async def setup(bot: OiBot):
    await bot.add_cog(Image(bot))
