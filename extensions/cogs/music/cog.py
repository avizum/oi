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

import asyncio
import contextlib
import datetime
import logging
import math
import urllib
import urllib.parse
from typing import Annotated, cast, Literal, TYPE_CHECKING

import discord
import wavelink
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Range
from wavelink import ExtrasNamespace as Extras
from wavelink import QueueMode

import core
from utils.helpers import format_seconds
from utils.paginators import Paginator

from .checks import is_in_channel, is_in_voice, is_manager, is_not_deafened
from .player import Player
from .views import LyricPageSource, QueuePageSource

if TYPE_CHECKING:
    from core import OiBot

    from .types import PlayerContext, TrackEnd, TrackException, TrackStart, TrackStuck


__all__ = ("Music",)
_log = logging.getLogger("oi.music")


MENTIONS = discord.AllowedMentions.none()
EXTRAS = dict(update_after=True)


SEARCH_TYPES = Literal[
    "YouTube",
    "YouTube Music",
    "Spotify",
    "SoundCloud",
    "Apple Music",
    "Deezer",
]


class ConvertTime(app_commands.Transformer):
    def base(self, ctx: PlayerContext, argument: int | str) -> int:
        with contextlib.suppress(ValueError):
            argument = int(argument)
        if isinstance(argument, int):
            return argument
        if isinstance(argument, str):
            try:
                time_ = datetime.datetime.strptime(argument, "%M:%S")
                delta = time_ - datetime.datetime(1900, 1, 1)
                return int(delta.total_seconds())
            except ValueError as e:
                raise commands.BadArgument("Time must be in MM:SS format.") from e

    async def convert(self, ctx: PlayerContext, argument: int | str) -> int:
        return self.base(ctx, argument)

    async def transform(self, itn: discord.Interaction, argument: int | str) -> int:
        ctx = itn._baton
        return self.base(ctx, argument)


Time = Annotated[int, ConvertTime]


class Music(core.Cog):
    """
    Music commands for your server.
    """

    def __init__(self, bot: OiBot) -> None:
        self.bot: OiBot = bot
        self.next_cooldown = commands.CooldownMapping.from_cooldown(3, 10, type=commands.BucketType.guild)

    @property
    def display_emoji(self) -> str:
        return "\U0001f3b5"

    async def cog_check(self, _: PlayerContext) -> bool:
        try:
            wavelink.Pool.get_node()
        except wavelink.InvalidNodeException as e:
            raise commands.CheckFailure("Music server is down. Please try again later.") from e
        return True

    @core.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        node: wavelink.Node = payload.node

        if payload.resumed:
            return
        else:
            for vc in node.players.values():
                self.bot.loop.create_task(self._reconnect(vc))  # type: ignore # all node players are type Player

    @core.Cog.listener()
    async def on_wavelink_track_end(self, payload: TrackEnd) -> None:
        vc = payload.player
        if vc is None:
            return
        elif vc.autoplay == wavelink.AutoPlayMode.enabled:
            return

        vc.skip_votes.clear()

        try:
            await vc.play(vc.queue.get())
        except wavelink.QueueEmpty:
            if vc.controller:
                await vc.controller.update()

    @core.Cog.listener()
    async def on_wavelink_track_start(self, payload: TrackStart) -> None:
        vc = payload.player

        if not vc:
            return

        self.bot.songs_played += 1

        track = payload.original
        if vc.autoplay == wavelink.AutoPlayMode.enabled and not getattr(track.extras, "requester", None):
            duration = "LIVE" if track.is_stream else format_seconds(track.length / 1000)
            suffix = f" - {track.author}" if track.author not in track.title else ""
            track.extras = Extras(
                requester="Suggested",
                requester_id=0,
                duration=duration,
                hyperlink=f"[{track.title}{suffix}](<{track.uri}>)",
            )
        await vc.invoke_controller(payload.original)

    @core.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: TrackStuck) -> None:
        vc = payload.player

        if not vc:
            return

        await vc.ctx.send("Track got stuck. Skipping.")
        await vc.skip()

    @core.Cog.listener()
    async def on_wavelink_track_exception(self, payload: TrackException):
        vc = payload.player
        track = payload.track
        exception = payload.exception

        if not vc or vc and vc.locked:
            return

        _log.error(
            f"Lavalink exception occured: {track.title} ({track.source}:{track.identifier}) in guild ID {vc.ctx.guild.id}\n"
            f"Message: {exception.get('message')}\nSeverity: {exception.get('severity')}"
        )

        cooldown = self.next_cooldown.update_rate_limit(vc.ctx)
        if cooldown:
            vc.locked = True
            _log.error(f"Player in guild id {vc.ctx.guild.id} disconnected: exception threshold reached.")
            with contextlib.suppress(discord.HTTPException):
                await vc.ctx.send(
                    "Sorry, your player has been disconnected due to a potential server issue. Please try again later.\n"
                    f"-# *(You can reconnect the player using {self.connect.mention})*"
                )
            await vc.disconnect(force=True)
            return
        # In some cases, track.hyperlink can possibly be unset when
        # wavelink_track_exception is called before wavelink_track start.
        await vc.ctx.send(f"An error occured while playing {getattr(track.extras, "hyperlink", track.title)}.")

    @core.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or not message.guild.voice_client:
            return

        vc = cast(Player, message.guild.voice_client)
        if vc.controller:
            vc.controller.counter += 2 if message.author.bot else 1

    @core.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or not message.guild.voice_client:
            return

        vc = cast(Player, message.guild.voice_client)
        controller = vc.controller
        if controller and controller.message and controller.message.id == message.id:
            controller.message = None

    @core.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        vc = cast(Player, member.guild.voice_client)
        if vc is None or member.bot:
            return

        if before.channel == after.channel:
            return

        if not vc.dj_enabled or vc.dj_role:
            return

        if member == vc.manager and after.channel != vc.channel or not vc.manager and after.channel == vc.channel:
            manager: discord.Member | None = next((mem for mem in vc.channel.members if not mem.bot), None)
            if manager:
                await vc.ctx.send(f"The new DJ is {manager.mention}.", reply=False, allowed_mentions=MENTIONS)
            vc.manager = manager

    async def cog_after_invoke(self, ctx: PlayerContext) -> None:
        update_after = ctx.command.extras.get("update_after", False)
        vc = ctx.voice_client
        if not vc:
            return
        if update_after and vc.controller:
            await vc.controller.update(ctx.interaction)
        if vc.ctx.interaction and ctx.interaction:
            vc.ctx.interaction = ctx.interaction

    async def _connect(self, ctx: PlayerContext) -> Player | None:
        assert ctx.author.voice is not None
        channel = ctx.author.voice.channel
        assert channel is not None
        if ctx.voice_client:
            await ctx.send(f"Already connected to {ctx.voice_client.channel.mention}")
            vc = ctx.voice_client
            return
        try:
            vc = Player(ctx=ctx)
            await channel.connect(cls=vc, self_deaf=True)  # type: ignore
            await ctx.send(f"Connected to {vc.channel.mention}")
            if isinstance(channel, discord.StageChannel):
                with contextlib.suppress(discord.Forbidden):
                    await ctx.me.edit(suppress=False)
        except wavelink.ChannelTimeoutException:
            await ctx.send(f"Timed out while trying to connect to {vc.channel.mention}")
            return
        await vc._set_player_settings()
        return vc

    @core.command()
    @is_not_deafened()
    @is_in_voice(bot=False)
    @core.bot_has_guild_permissions(connect=True, speak=True)
    async def connect(self, ctx: PlayerContext) -> Player | None:
        """
        Connects to a voice channel or stage.
        """
        return await self._connect(ctx)

    @core.command()
    @is_manager()
    @is_in_voice()
    async def disconnect(self, ctx: PlayerContext) -> None:
        """
        Disconnects the player from the channel.
        """
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected. Goodbye!")

    async def _reconnect(self, voice_client: Player) -> bool:
        channel = voice_client.channel
        try:
            await voice_client.disconnect()
            voice_client.locked = True

            await asyncio.sleep(1)

            vc: Player = await channel.connect(cls=Player(ctx=voice_client.ctx))  # type: ignore
            vc.queue.put(list(voice_client.queue))
            if voice_client.current:
                vc.queue.put_at(0, voice_client.current)
                await vc.play(vc.queue.get())
                await vc.seek(int(voice_client.position) - 1)
            return True
        except Exception as exc:
            _log.error("Ignoring exception while reconnecting player:", exc_info=exc)
            return False

    @core.command()
    @is_manager()
    @is_in_channel()
    @is_in_voice()
    async def reconnect(self, ctx: PlayerContext):
        """
        Reconnects your player without loss of the queue and song position.
        """
        if await self.bot.is_owner(ctx.author) and not ctx.interaction:
            to_reconnect: list[asyncio.Task] = []
            for vc in self.bot.voice_clients:
                to_reconnect.append(self.bot.loop.create_task(self._reconnect(vc)))  # type: ignore # all voice clients are type Player
            gathered = await asyncio.gather(*to_reconnect)
            failed = len([result for result in gathered if result is False])
            if failed:
                return await ctx.send(f"{failed} players failed to reconnect.")
            return await ctx.send("Finished reconnecting all players.")
        await self._reconnect(ctx.voice_client)
        return await ctx.send("Reconnected.")

    @core.command(hidden=True)
    @app_commands.guilds(768895735764221982, 866891524319084587)
    @core.has_permissions(ban_members=True)
    @core.is_owner()
    async def refresh(self, ctx: PlayerContext, po_token: str, visitor_data: str):
        """
        Refreshes the internal tokens used by Lavalink.
        """
        try:
            node = wavelink.Pool.get_node("OiBot")
            await node.send("POST", path="youtube", data={"poToken": po_token, "visitorData": visitor_data})
            await ctx.send("Set data.")
        except (wavelink.LavalinkException, wavelink.NodeException) as exc:
            await ctx.send(f"Could not set data: {exc}")

    @core.command(extras=EXTRAS)
    @is_not_deafened()
    @is_in_voice(bot=False)
    @core.bot_has_guild_permissions(connect=True, speak=True)
    @core.describe(
        query="What to search for.",
        source="Where to search.",
        play_now="Whether to play the song now.",
        play_next="Whether to play the song next.",
        shuffle="Whether to shuffle the queue.",
    )
    async def play(
        self,
        ctx: PlayerContext,
        *,
        query: str,
        source: SEARCH_TYPES = "YouTube Music",
        play_now: bool = False,
        play_next: bool = False,
        shuffle: bool = False,
    ) -> None:
        """
        Play a song from a selected source.
        """
        vc = ctx.voice_client or await self._connect(ctx)

        if vc is None:
            await ctx.send(f"Could not join your channel. Use {self.connect.mention} to continue.")
            return

        search = await vc.fetch_tracks(query, source)
        if not search:
            await ctx.send("No tracks found...")
            return

        await is_in_channel().predicate(ctx)

        if play_now or play_next or shuffle:
            await is_manager().predicate(ctx)

        requester = str(ctx.author)
        requester_id = ctx.author.id

        if isinstance(search, wavelink.Playlist):
            for track in search:
                suffix = f" - {track.author}" if track.author not in track.title else ""
                duration = "LIVE" if track.is_stream else format_seconds(track.length / 1000)
                track.extras = Extras(
                    requester=requester,
                    requester_id=requester_id,
                    duration=duration,
                    hyperlink=f"[{track.title}{suffix}](<{track.uri}>)",
                )
            if play_now or play_next:
                search.tracks.reverse()
                added = 0
                for track in search:
                    vc.queue.put_at(0, track)
                    added += 1
                end = "beginning of the queue."
            else:
                added = vc.queue.put(search)
                end = "queue."

            url = search.url or query
            hyperlink = f"[{search.name}](<{url}>)"
            embed = discord.Embed(
                title="Enqueued Playlist",
                description=f"Added {hyperlink} with {added} tracks to the {end}",
            )
        else:
            suffix = f" - {search.author}" if search.author not in search.title else ""
            duration = "LIVE" if search.is_stream else format_seconds(search.length / 1000)
            search.extras = Extras(
                requester=requester,
                requester_id=requester_id,
                duration=duration,
                hyperlink=f"[{search.title}{suffix}](<{search.uri}>)",
            )
            if play_now or play_next:
                vc.queue.put_at(0, search)
                end = "beginning of the queue."
            else:
                vc.queue.put(search)
                end = "queue."
            embed = discord.Embed(
                title="Enqueued Track",
                description=f"Added {search.extras.hyperlink} to the {end}",
            )
        embed.set_thumbnail(url=search.artwork)

        await ctx.send(embed=embed)

        if shuffle:
            vc.queue.shuffle()

        if not vc.current:
            await vc.play(vc.queue.get())
        elif vc.paused:
            await vc.pause(False)
        elif play_now:
            await vc.skip()

    @core.command(extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def pause(self, ctx: PlayerContext):
        """
        Pauses playback of the player.
        """
        vc = ctx.voice_client

        if not vc.current:
            return await ctx.send("There is nothing playing.")

        if vc.paused:
            return await ctx.send("Player is already paused.")

        await vc.pause(True)
        await ctx.send("Paused the player.")

    @core.command(extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def resume(self, ctx: PlayerContext):
        """
        Resumes playback of the player.
        """
        vc = ctx.voice_client

        if not vc.current:
            return await ctx.send("There is nothing playing.")

        if not vc.paused:
            return await ctx.send("Player is not paused.")

        await vc.pause(False)
        await ctx.send("Unpaused the player.")

    @core.command(extras=EXTRAS)
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def skip(self, ctx: PlayerContext):
        """
        Skips the song.

        If you are a DJ or track requester, the track will be skipped.
        Otherwise, a vote will be added in order to skip.
        """
        vc = ctx.voice_client

        if not vc.current:
            return await ctx.send("There is nothing playing.")

        try:
            await is_manager().predicate(ctx)
            await vc.skip()
            await ctx.send(f"{ctx.author} has skipped the track.")
            return
        except commands.CheckFailure:
            pass

        if ctx.author.id == vc.current.extras.requester_id:
            await vc.skip()
            await ctx.send(f"Track requester {ctx.author} has skipped the track.")
        else:
            required = math.ceil(len(vc.channel.members) / 2)
            if ctx.author.id in vc.skip_votes:
                await ctx.send("You already voted to skip the track.", ephemeral=True)
                return
            vc.skip_votes.add(ctx.author.id)
            if len(vc.skip_votes) >= required:
                await vc.skip()
                await ctx.send(f"Vote to skip passed ({required} of {required}). Skipping.")
                return
            await ctx.send(f"Voted to skip. ({len(vc.skip_votes)}/{required})", ephemeral=True)

    @core.command(extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(time="Where to seek in MM:SS format.")
    async def seek(self, ctx: PlayerContext, time: Time):
        """
        Seek positions in the current track.
        """
        vc = ctx.voice_client

        await vc.seek(time * 1000)
        await ctx.send(f"Seeked to {format_seconds(time)}.")

    @core.group()
    async def queue(self, ctx: PlayerContext):
        """
        Queue commands.
        """
        await ctx.send_help(ctx.command)

    @queue.command(name="show")
    @is_in_channel()
    @is_in_voice(author=False)
    async def queue_show(self, ctx: PlayerContext):
        """
        Shows the queue in a paginated format.
        """
        vc = ctx.voice_client

        if len(vc.queue) == 0:
            return await ctx.send("Nothing is in the queue.")

        source = QueuePageSource(vc)
        paginator = Paginator(source, ctx=ctx, delete_message_after=True)
        await paginator.start()

    @queue.command(name="shuffle", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def queue_shuffle(self, ctx: PlayerContext):
        """
        Shuffles the queue randomly.
        """
        vc = ctx.voice_client

        if not vc.queue:
            return await ctx.send("The queue is empty.")

        vc.queue.shuffle()
        await ctx.send("Shuffled the queue.")

    @queue.command(name="loop", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def queue_loop(self, ctx: PlayerContext):
        """
        Loops all the songs in the queue.
        """
        vc = ctx.voice_client

        vc.queue.mode = QueueMode.loop_all
        await ctx.send("Enabled queue loop.")

    @queue.command(name="clear", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def queue_clear(self, ctx: PlayerContext):
        """
        Clears the queue and the queue history.
        """
        vc = ctx.voice_client

        if not vc.queue:
            return await ctx.send("The queue is empty.")

        vc.queue.reset()
        await ctx.send("Cleared the queue.")

    @core.group()
    async def player(self, ctx: PlayerContext):
        """
        Music player commands.
        """
        await ctx.send_help(ctx.command)

    @player.group(name="dj")
    async def player_dj(self, ctx: PlayerContext):
        """
        DJ settings commands.
        """
        await ctx.send_help(ctx.command)

    @player_dj.command(name="enable")
    @core.has_guild_permissions(manage_guild=True)
    async def player_dj_enable(self, ctx: PlayerContext):
        """
        Enables DJ.
        """
        vc = ctx.voice_client
        settings = self.bot.player_settings[ctx.guild.id]
        if settings["dj_enabled"] is True:
            return await ctx.send("DJ is already enabled.")

        query = """
            UPDATE player_settings
            SET dj_enabled=$1
            WHERE guild_id=$2
            RETURNING *
        """
        settings = await ctx.bot.pool.fetchrow(query, True, ctx.guild.id)
        self.bot.player_settings[ctx.guild.id] = settings
        if vc:
            vc.dj_enabled = True
        return await ctx.send("Enabled DJ.")

    @player_dj.command(name="disable")
    @core.has_guild_permissions(manage_guild=True)
    async def player_dj_disable(self, ctx: PlayerContext):
        """
        Disables DJ.
        """
        vc = ctx.voice_client
        settings = self.bot.player_settings[ctx.guild.id]
        if settings["dj_enabled"] is False:
            return await ctx.send("DJ is already disabled.")

        query = """
            UPDATE player_settings
            SET dj_enabled=$1
            WHERE guild_id=$2
            RETURNING *
        """
        settings = await ctx.bot.pool.fetchrow(query, False, ctx.guild.id)
        self.bot.player_settings[ctx.guild.id] = settings
        if vc:
            vc.dj_enabled = False
        return await ctx.send("Disabled DJ.")

    @player_dj.command(name="role")
    @core.has_guild_permissions(manage_guild=True)
    @core.describe(role="The role to set as DJ")
    async def player_dj_role(self, ctx: PlayerContext, role: discord.Role | None):
        """
        Sets the DJ role. If not set, the DJ is whoever calls Oi into the channel first.
        """
        vc = ctx.voice_client
        settings = self.bot.player_settings[ctx.guild.id]
        if role and settings["dj_role"] == role.id:
            return await ctx.send(f"DJ is already set to {role.mention}.", allowed_mentions=MENTIONS)

        conf = None

        if not vc.dj_enabled:
            conf = await ctx.confirm(message="DJ is disabled. Would you like to enable it and set the DJ role?")
            if not conf.result:
                return await conf.message.edit(content="DJ will remain disabled.", view=None)

        role_id = role.id if role else 0
        query = """
            UPDATE player_settings
            SET dj_role=$1, dj_enabled=$2
            WHERE guild_id=$3
            RETURNING *
        """
        settings = await ctx.bot.pool.fetchrow(query, role_id, True, ctx.guild.id)
        self.bot.player_settings[ctx.guild.id] = settings
        if vc:
            vc.dj_role = role
            vc.dj_enabled = True
        if not role:
            message = "DJ role has been unset. The first user of each session will be set as DJ."
            if conf:
                return await conf.message.edit(content=message, view=None)
            return await ctx.send(message)
        message = f"DJ role set to {role.mention}."
        if conf:
            return await conf.message.edit(content=message, allowed_mentions=MENTIONS, view=None)
        return await ctx.send(message, allowed_mentions=MENTIONS)

    @player.command(name="current")
    @is_in_voice()
    async def player_current(self, ctx: PlayerContext):
        """
        Shows the current song, or move the bound channel to another channel.
        """
        vc = ctx.voice_client

        if not vc.current:
            return await ctx.send("There is nothing playing.")

        if ctx.channel != vc.ctx.channel:
            try:
                await is_manager().predicate(ctx)
                await vc.ctx.send(f"{ctx.author} moved the controller to {ctx.channel.mention}")
            except commands.CheckFailure:
                raise commands.CheckFailure(f"This command can only be ran in {vc.ctx.channel.mention}, not here.")

        if vc.controller:
            vc.controller.counter = 10

        vc.ctx = ctx
        await vc.invoke_controller(vc.current)

    @player.command(name="loop", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(mode="Whether to loop the queue, track, or disable.")
    async def player_loop(self, ctx: PlayerContext, mode: Literal["track", "queue", "off"]):
        """
        Options on looping.
        """
        vc = ctx.voice_client

        if not vc.current:
            return await ctx.send("There is nothing playing.")

        if mode == "track":
            vc.queue.mode = QueueMode.loop
            await ctx.send(f"Now looping {vc.current.extras.hyperlink}")
        elif mode == "queue":
            vc.queue.mode = QueueMode.loop_all
            await ctx.send("Enabled queue loop.")
        else:
            vc.queue.mode = QueueMode.normal
            await ctx.send("Disabled Loop.")

    @player.command(name="volume")
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(volume="The new volume of the player.")
    async def player_volume(self, ctx: PlayerContext, volume: Range[int, 1, 200]):
        """
        Change the volume of the player.
        """
        vc = ctx.voice_client

        await vc.set_volume(volume)
        await ctx.send(f"Volume set to {volume}%")

    @player.command(name="autoplay", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(state="Whether to autoplay.")
    async def player_autoplay(self, ctx: PlayerContext, state: bool):
        """
        Enable or disable autoplay in this session.
        """
        vc = ctx.voice_client
        if state:
            vc.autoplay = wavelink.AutoPlayMode.enabled
            await ctx.send("Autoplay is now enabled.")
        else:
            vc.autoplay = wavelink.AutoPlayMode.disabled
            await ctx.send("Autoplay is now disabled.")

    @player.group(name="filter")
    async def player_filter(self, ctx: PlayerContext):
        """Filter commands."""
        await ctx.send_help(ctx.command)

    @player_filter.command(name="speed")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(speed="The speed multiplier.")
    async def player_filter_speed(self, ctx: PlayerContext, speed: Range[float, 0.25, 3.0]):
        """
        Change the speed of the player.
        """
        vc = ctx.voice_client

        filters = vc.filters

        filters.timescale.set(speed=speed)
        await vc.set_filters(filters)

        await ctx.send(f"Set Speed filter to {speed}x speed.")

    @player_filter.command(name="pitch")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(pitch="How much to change the pitch.")
    async def player_filter_pitch(self, ctx: PlayerContext, pitch: Range[float, 0.1, 5.0]):
        """
        Change the pitch of the player.
        """
        vc = ctx.voice_client

        filters = vc.filters

        filters.timescale.set(pitch=pitch)
        await vc.set_filters(filters)

        await ctx.send(f"Set Pitch filter to {pitch}.")

    @player_filter.command(name="rate")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(rate="How much to change the speed and pitch.")
    async def player_filter_rate(self, ctx: PlayerContext, rate: Range[float, 0.75, 4.5]):
        """
        Change the Speed and the Pitch of the player.
        """
        vc = ctx.voice_client

        filters = vc.filters

        filters.timescale.set(rate=rate)
        await vc.set_filters(filters)

        await ctx.send(f"Set Speed filter to {rate}.")

    @player_filter.command(name="tremolo")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(frequency="How frequently the volume should change.", depth="How much the volume should change.")
    async def player_filter_tremolo(
        self, ctx: PlayerContext, frequency: Range[float, 0.1, 100.0], depth: Range[float, 0.1, 1.0]
    ):
        """
        Adds a termolo effect to the player.
        """
        vc = ctx.voice_client

        filters = vc.filters

        filters.tremolo.set(frequency=frequency, depth=depth)
        await vc.set_filters(filters)

        await ctx.send(f"Set Tremolo filter to {frequency} frequency and {depth} depth.")

    @player_filter.command(name="vibrato")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(frequency="How frequent the the pitch should change.", depth="How much the pitch should change.")
    async def player_filter_vibrato(
        self, ctx: PlayerContext, frequency: Range[float, 0.1, 14.0], depth: Range[float, 0.1, 1.0]
    ):
        """
        Adds a vibrato effect to the player.
        """
        vc = ctx.voice_client
        filters = vc.filters

        filters.vibrato.set(frequency=frequency, depth=depth)
        await vc.set_filters(filters)

        await ctx.send(f"Set Vibrato filter to {frequency} frequency and {depth} depth.")

    @player_filter.command(name="karaoke")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(
        level="How strong the filter should be.",
        mono_level="How strong the filter should be in mono.",
        band="The filterband in Hz.",
        width="The filter's width.",
    )
    async def player_filter_karaoke(
        self,
        ctx: PlayerContext,
        level: Range[float, 0.1, 1.0],
        mono_level: Range[float, 0.1, 1.0] = 1.0,
        band: float = 220.0,
        width: float = 100.0,
    ):
        """
        Adds an effect that will try to remove vocals from the music.
        """
        vc = ctx.voice_client
        filters = vc.filters

        filters.karaoke.set(level=level, mono_level=mono_level, filter_band=band, filter_width=width)
        await vc.set_filters(filters)

        await ctx.send("Set Karaoke filter.")

    @player_filter.command(name="lowpass")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(smoothing="How much smoothing to apply.")
    async def player_filter_lowpass(self, ctx: PlayerContext, smoothing: Range[float, 0.1, 60.0]):
        """
        Allows only low frequencies to pass through.
        """
        vc = ctx.voice_client
        filters = vc.filters

        filters.low_pass.set(smoothing=smoothing)
        await vc.set_filters(filters)

        await ctx.send(f"Set Lowpass filter, smoothing set to {smoothing}")

    @player_filter.command(name="rotation")
    @core.has_voted()
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def player_filter_rotation(self, ctx: PlayerContext):
        """
        Creates a rotation effect in the player.
        """
        vc = ctx.voice_client
        filters = vc.filters

        filters.rotation.set(rotation_hz=0.2)
        await vc.set_filters(filters)

        await ctx.send("Set Rotation filter.")

    @player_filter.command(name="reset")
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def player_filter_reset(self, ctx: PlayerContext):
        """
        Removes all the filters.
        """
        vc = ctx.voice_client

        await vc.set_filters(None)

        await ctx.send("Reset all filters.")

    @core.command()
    @core.has_voted()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(
        text="What to say in the voice channel.",
        voice="Which voice to use.",
        translate="Whether to translate text to the native language of the voice.",
        speed="How slow or fast the speech should be.",
    )
    async def tts(
        self,
        ctx: PlayerContext,
        *,
        text: commands.Range[str, 1, 2000],
        voice: str = "Carter",
        translate: bool = False,
        speed: commands.Range[float, 0.5, 10.0] = 1.0,
    ):
        """
        Text to speech in voice channel.
        """
        vc = ctx.voice_client

        if vc.current and not vc.paused:
            return await ctx.send("This command requires the player to be idle.", ephemeral=True)

        current = None
        start = 0
        if vc.current:
            current = vc.current
            start = vc.position

        text = urllib.parse.quote(text)

        search = await wavelink.Playable.search(
            f"ftts://{text}?voice={voice}&translate={str(translate).lower()}&speed={speed}", source=None
        )
        if not search:
            return await ctx.send("Could not load speech.", ephemeral=True)

        track = search[0]
        track.extras = Extras(
            requester=str(ctx.author),
            requester_id=ctx.author.id,
            duration="N/A",
            hyperlink="TTS query",
        )

        await vc.play(track, add_history=False, paused=False)
        await self.bot.wait_for("wavelink_track_end", check=lambda pl: pl.player.channel == vc.channel)
        if current:
            await vc.play(current, start=start, paused=True, add_history=False)

    @core.command()
    @core.has_voted()
    @core.describe(search="The song to search for.")
    async def lyrics(self, ctx: PlayerContext, *, search: str | None = None):
        """
        Gets the lyrics for a song.

        If no query is provided, the lyrics for the current song (if any) will be shown.
        """
        vc = ctx.voice_client

        if not search and not vc:
            raise commands.BadArgument("No argument provided for search.")

        elif not search:
            if vc and not vc.current:
                raise commands.BadArgument("There is no song playing. Please enter a search query or play a song.")

            assert vc.current is not None
            title = vc.current.title
            lyrics_data = await vc.fetch_current_lyrics()

        else:
            fetch = await Player.fetch_lyrics(search)
            if not fetch:
                raise commands.BadArgument("No results found matching your search.")
            title, lyrics_data = fetch

        if not lyrics_data or lyrics_data and not lyrics_data["text"]:
            print(lyrics_data)
            raise commands.BadArgument("No results found matching your search.")
        lyrics = lyrics_data["text"]
        pag = commands.Paginator(max_size=320)
        for line in lyrics.splitlines():
            pag.add_line(line)

        source = LyricPageSource(title, pag)
        paginator = Paginator(source, ctx=ctx, delete_message_after=True)
        await paginator.start()
