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
import logging
import math
from collections import defaultdict
from typing import cast, Literal, TYPE_CHECKING
from urllib import parse

import discord
import wavelink
from asyncpg import UniqueViolationError
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Range
from rapidfuzz import process
from wavelink import ExtrasNamespace as Extras, QueueMode

import core
from utils.helpers import format_seconds
from utils.paginators import Paginator
from utils.types import Playlist as PlaylistD, Song as SongD

from .player import Player
from .utils import (
    find_song_matches,
    hyperlink_song,
    is_in_channel,
    is_in_voice,
    is_manager,
    is_not_deafened,
    Playlist,
    Song,
    Time,
)
from .views import LyricPageSource, PlaylistInfoModal, PlaylistModalView, PlaylistPageSource, QueuePageSource

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


type Interaction = discord.Interaction[OiBot]


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
            vc.set_extras(track, requester="Suggested", requester_id=0)
        await vc.invoke_controller(payload.original)

    @core.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: TrackStuck) -> None:
        vc = payload.player

        if not vc:
            return

        await vc.ctx.send("Track got stuck. Skipping.", no_tips=True)
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
                    f"-# *(You can reconnect the player using {self.connect.mention})*",
                    no_tips=True,
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

    @core.Cog.listener("on_message_delete")
    @core.Cog.listener("on_bulk_message_delete")
    async def message_delete(self, messages: discord.Message | list[discord.Message]) -> None:
        message = messages[0] if isinstance(messages, list) else messages
        if message.guild is None or not message.guild.voice_client:
            return

        vc = cast(Player, message.guild.voice_client)

        if not vc.controller:
            return
        elif vc.controller and vc.controller.message is not None:
            if isinstance(messages, list):
                message_deleted = discord.utils.get(messages, id=vc.controller.message.id) is not None
            else:
                message_deleted = vc.controller.message.id == message.id

            if message_deleted:
                vc.controller.message = None

    @core.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
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
                await vc.ctx.send(f"The new DJ is {manager.mention}.", reply=False, allowed_mentions=MENTIONS, no_tips=True)
            vc.manager = manager

    async def cog_after_invoke(self, ctx: PlayerContext) -> None:
        update_after = ctx.command.extras.get("update_after", False)
        vc = ctx.voice_client
        if not vc:
            return
        if update_after and vc.controller:
            invoke = not ctx.command.qualified_name == "skip"
            await vc.controller.update(ctx.interaction, invoke=invoke)

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
        """Connects to a voice channel or stage."""
        return await self._connect(ctx)

    @core.command()
    @is_manager()
    @is_in_voice()
    async def disconnect(self, ctx: PlayerContext) -> None:
        """Disconnects the player from the channel."""
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected. Goodbye!")

    async def _reconnect(self, voice_client: Player) -> bool:
        channel = voice_client.channel
        try:
            position = voice_client.position

            vc = Player(ctx=voice_client.ctx)
            vc.queue.put(list(voice_client.queue))
            if voice_client.current:
                vc.queue.put_at(0, voice_client.current)

            await voice_client.disconnect()
            await asyncio.sleep(1)
            await channel.connect(cls=vc)  # type: ignore

            if vc.queue:
                await vc.play(vc.queue.get(), start=position)
            return True
        except Exception as exc:
            _log.error("Ignoring exception while reconnecting player:", exc_info=exc)
            return False

    @core.command()
    @is_manager()
    @is_in_channel()
    @is_in_voice()
    async def reconnect(self, ctx: PlayerContext):
        """Reconnects your player without loss of the queue and song position."""
        if await self.bot.is_owner(ctx.author) and not ctx.interaction:
            to_reconnect: list[asyncio.Task] = []
            for vc in self.bot.voice_clients:
                to_reconnect.append(self.bot.loop.create_task(self._reconnect(vc)))  # type: ignore # all voice clients are type Player
            gathered = await asyncio.gather(*to_reconnect)
            failed = len([result for result in gathered if result is False])
            if failed:
                return await ctx.send(f"{failed} players failed to reconnect.")
            return await ctx.send("Finished reconnecting all players.")
        async with ctx.typing():
            await self._reconnect(ctx.voice_client)
            return await ctx.send("Reconnected.")

    @core.command(hidden=True)
    @app_commands.guilds(768895735764221982, 866891524319084587)
    @core.has_permissions(ban_members=True)
    @core.is_owner()
    async def refresh(self, ctx: PlayerContext, po_token: str, visitor_data: str):
        """Refreshes the internal tokens used by Lavalink."""
        try:
            node = wavelink.Pool.get_node("OiBot")
            await node.send("POST", path="youtube", data={"poToken": po_token, "visitorData": visitor_data})
            await ctx.send("Set data.")
        except (wavelink.LavalinkException, wavelink.NodeException) as exc:
            await ctx.send(f"Could not set data: {exc}")

    @core.command()
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
        """Play a song from a selected source."""
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
                vc.set_extras(track, requester=requester, requester_id=requester_id)

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
            vc.set_extras(search, requester=requester, requester_id=requester_id)

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
            return
        elif vc.paused:
            await vc.pause(False)
        elif play_now:
            await vc.skip()

        if vc.controller:
            await vc.controller.update(ctx.interaction)

    @core.command(extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def pause(self, ctx: PlayerContext):
        """Pauses playback of the player."""
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
        """Resumes playback of the player."""
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
        """Seek positions in the current track."""
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
        """Shows the queue in a paginated format."""
        vc = ctx.voice_client

        if len(vc.queue) == 0:
            return await ctx.send("Nothing is in the queue.")

        source = QueuePageSource(vc)
        paginator = Paginator(source, ctx=ctx, delete_message_after=True)
        await paginator.start()

    @queue.command(name="remove", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    @core.describe(item="The track to remove from the queue.")
    async def queue_remove(self, ctx: PlayerContext, item: str):
        """
        Removes a song from the queue.

        If there are multiple of the same track, all of them will be removed.
        """
        vc = ctx.voice_client

        if not vc.queue:
            return await ctx.send("There is nothing in the queue.")

        tracks = [track for track in vc.queue if item.lower() == track.title.lower()]

        if not tracks:
            return await ctx.send("Could not find any tracks with that name.")

        vc.queue.remove(tracks[0], count=len(tracks))
        all_instances = "all instances of" if len(tracks) > 1 else ""
        await ctx.send(f"Removed {all_instances}{tracks[0].extras.hyperlink} from the queue.")

    @queue_remove.autocomplete("item")
    async def queue_remove_autocomplete(self, itn: Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not itn.guild:
            return [app_commands.Choice(name="If you see this, I'm telling on you.", value="crazy stuff")]
        elif not itn.guild.voice_client:
            return [app_commands.Choice(name="There is no player connected", value="disconnected")]

        assert isinstance(itn.guild.voice_client, Player)

        return [
            app_commands.Choice(name=track.title, value=track.title)
            for track in itn.guild.voice_client.queue
            if current.lower() in track.title.lower()
        ][:25]

    @queue.command(name="shuffle", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def queue_shuffle(self, ctx: PlayerContext):
        """Shuffles the queue randomly."""
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
        """Loops all the songs in the queue."""
        vc = ctx.voice_client

        vc.queue.mode = QueueMode.loop_all
        await ctx.send("Enabled queue loop.")

    @queue.command(name="clear", extras=EXTRAS)
    @is_manager()
    @is_not_deafened()
    @is_in_channel()
    @is_in_voice()
    async def queue_clear(self, ctx: PlayerContext):
        """Clears the queue and the queue history."""
        vc = ctx.voice_client

        if not vc.queue:
            return await ctx.send("The queue is empty.")

        vc.queue.reset()
        await ctx.send("Cleared the queue.")

    @core.group(fallback="show")
    @app_commands.describe(playlist="The playlist to show information of")
    async def playlist(self, ctx: PlayerContext, playlist: Playlist):
        """
        Shows a playlist.
        """
        source = PlaylistPageSource(playlist)
        paginator = Paginator(source, ctx=ctx, delete_message_after=True)
        await paginator.start()

    @playlist.command(name="play")
    @core.describe(playlist="The playlist to show information of.")
    @is_not_deafened()
    @is_in_voice(bot=False)
    @core.bot_has_guild_permissions(connect=True, speak=True)
    @core.describe(
        playlist="The playlist to play.",
        play_now="Whether to start playing the playlist now.",
        play_next="Whether to play the playlist next.",
        shuffle="Whether to shuffle the queue.",
    )
    async def playlist_play(
        self,
        ctx: PlayerContext,
        *,
        playlist: Playlist,
        play_now: bool = False,
        play_next: bool = False,
        shuffle: bool = False,
    ):
        """
        Adds a playlist to the queue.

        This command is similar to the play command.
        """
        vc = ctx.voice_client or await self._connect(ctx)

        if vc is None:
            await ctx.send(f"Could not join your channel. Use {self.connect.mention} to continue.")
            return

        tracks: list[wavelink.Playable] = []
        for song in playlist["songs"].values():
            track = await vc.decode_track(song["encoded"])
            if track:
                vc.set_extras(track, requester=str(ctx.author), requester_id=ctx.author.id)
                tracks.append(track)

        if play_now or play_next:
            tracks.reverse()
            added = 0
            for track in tracks:
                vc.queue.put_at(0, track)
                added += 1
            end = "beginning of the queue."
        else:
            added = vc.queue.put(tracks)
            end = "queue."

        embed = discord.Embed(
            title="Enqueued Personal Playlist", description=f"Added {playlist['name']} with {added} tracks to the {end}"
        )
        image = playlist["image"] or tracks[0].artwork
        embed.set_thumbnail(url=image)

        await ctx.send(embed=embed)

        if shuffle:
            vc.queue.shuffle()

        if not vc.current:
            await vc.play(vc.queue.get())
            return
        elif vc.paused:
            await vc.pause(False)
        elif play_now:
            await vc.skip()

        if vc.controller:
            await vc.controller.update()

    async def send_playlist_modal(
        self, *, ctx: PlayerContext, playlist: PlaylistD | None = None
    ) -> tuple[discord.Message | None, str, str]:
        if playlist:
            prefix = "Edit playlist "
            name = playlist["name"]
            title = f"{prefix}{name}"
            if len(name) > 31:  # 45 (max title length) - 13 (length of prefix)
                title = f"{prefix}{name[:28]}..."
        else:
            title = "Create a playlist"

        message: discord.Message | None = None
        if not ctx.interaction:
            action = "edit your" if playlist else "create a"
            view = PlaylistModalView(title=title, playlist=playlist, members=[ctx.author])
            message = await ctx.send(f"Click the button below to {action} playlist.", view=view)
            view.message = message
            await view.wait()
            url = view.url if view.url else ""
            return (message, view.name, url)
        name = playlist["name"] if playlist else None
        image = playlist.get("image") if playlist else None
        modal = PlaylistInfoModal(title=title, name=name, image=image)
        await ctx.interaction.response.send_modal(modal)
        await modal.wait()
        url = modal.url if modal.url else ""
        return (message, modal.name, url)

    @playlist.command(name="create")
    @core.describe(name="The name for your playlist.", image="The cover image that will be used for your playlist.")
    async def playlist_create(self, ctx: PlayerContext, name: Range[str, 1, 100] | None = None, image: str = ""):
        """Creates a playlist."""
        message: discord.Message | None = None
        if not name:
            message, name, image = await self.send_playlist_modal(ctx=ctx)

            if not name:
                # Name is an empty string when PlaylistModalView is sent and it times out.
                # At this point, we assume the user did not mean use the command and ignore it.
                return

        if image:
            res = parse.urlparse(image)
            if not all([res.scheme, res.netloc]):
                raise commands.BadArgument("Image URL provided is invalid.")

        query = """
            INSERT INTO playlists (id, name, author, image)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """

        # Because Playlists can be searched for with ID or name, they can not contain only digits.
        if name.isdigit():
            raise commands.BadArgument("Playlist names can not be only digits. Try adding a letter.")

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        gen_id = self.bot.id_generator.generate()
        try:
            playlist = await self.bot.pool.fetchrow(query, gen_id, name, ctx.author.id, image)
        except UniqueViolationError as exc:
            raise commands.BadArgument("You already have a playlist with that name.") from exc

        playlist_data: PlaylistD = dict(playlist)  # type: ignore
        playlist_data["songs"] = {}
        self.bot.cache.playlists[gen_id] = playlist_data  # type: ignore

        success = (
            f"Created playlist named: {name}\nUse {self.playlist_songs_add.mention} to add some songs to your playlist."
        )

        if message:
            return await message.edit(content=success)
        return await ctx.send(success)

    @playlist.group(name="songs")
    async def playlist_songs(self, ctx: PlayerContext, playlist: Playlist | None = None):
        """
        Shows a playlist's songs.
        """
        if not playlist:
            return await ctx.send_help(ctx.command)

        await ctx.invoke(self.playlist, playlist)

    @playlist_songs.command(name="add")
    @core.describe(
        playlist="The playlist to add a song to.",
        song="The song to add to the playlist.",
        source="The source to use to search if song is not saved by Oi.",
    )
    async def playlist_songs_add(
        self, ctx: PlayerContext, playlist: Playlist, song: Song, source: SEARCH_TYPES = "YouTube Music"
    ):
        """
        Adds a song to one of your playlists.

        Connect the player to search for tracks that Oi hasn't saved.
        """
        vc = ctx.voice_client

        if isinstance(song, str) and not vc:
            raise commands.CheckFailure(f"{self.connect.mention} to search for more songs.")

        if isinstance(song, str):
            search = await vc.fetch_tracks(song, source, save_tracks=False)
            if not search:
                return await ctx.send("No tracks found...")
            elif isinstance(search, wavelink.Playlist):
                return await ctx.send("Only individual songs can be added to a playlist.")
            song = (await vc.save_tracks([search]))[search.identifier]

        if song["id"] in playlist["songs"]:
            return await ctx.send(f"{hyperlink_song(song)} is already in the playlist.")

        query = """
            INSERT INTO playlist_songs (playlist_id, song_id, position)
            VALUES ($1,$2,$3)
        """
        position = len(playlist["songs"]) + 1
        await self.bot.pool.execute(query, playlist["id"], song["id"], position)
        song["position"] = position
        playlist["songs"][song["id"]] = song

        embed = discord.Embed(
            title="Added song to playlist",
            description=(
                f"{hyperlink_song(song)} was added to playlist {playlist["name"]}\n"
                f"There are now {len(playlist["songs"])} songs now in your playlist."
            ),
        )
        embed.set_thumbnail(url=playlist["image"])

        await ctx.send(embed=embed)

    @playlist_songs_add.autocomplete("song")
    async def playlist_add_song_autocomplete(self, itn: Interaction, current: str) -> list[app_commands.Choice[str]]:
        songs: dict[str, list[SongD]] = defaultdict(list)
        for song in itn.client.cache.songs.values():
            songs[song["title"].lower()].append(song)

        return find_song_matches(songs, current)

    @playlist_songs.command(name="remove")
    @core.describe(
        playlist="The playlist to remove a song from.",
        song="The song to add to the playlist.",
    )
    async def playlist_songs_remove(self, ctx: PlayerContext, playlist: Playlist, song: Song):
        """Removes a song from one of your playlists."""
        if isinstance(song, str):
            raise commands.BadArgument(f"Could not find song named {song}.")

        if song["id"] not in playlist["songs"]:
            raise commands.BadArgument(f"{hyperlink_song(song)} is not in playlist {playlist["name"]}.")

        query = """
            DELETE FROM playlist_songs
            WHERE playlist_id = $1 AND song_id = $2
        """

        await self.bot.pool.execute(query, playlist["id"], song["id"])
        del playlist["songs"][song["id"]]

        await ctx.send(f"Removed {hyperlink_song(song)} from playlist {playlist["name"]}")

    @playlist_songs_remove.autocomplete("song")
    async def playlist_remove_song_autocomplete(self, itn: Interaction, current: str) -> list[app_commands.Choice[str]]:
        songs: list[SongD] = []
        for playlist in itn.client.cache.playlists.values():
            if playlist["author"] == itn.user.id:
                songs.extend(playlist["songs"].values())

        songs_d: dict[str, list[SongD]] = defaultdict(list)
        for song in songs:
            songs_d[song["title"].lower()].append(song)

        return find_song_matches(songs_d, current)

    @playlist.command(name="delete")
    @core.describe(playlist="The playlist to delete.")
    async def playlist_delete(self, ctx: PlayerContext, playlist: Playlist):
        """Deletes one of your playlists."""
        query = "DELETE FROM playlists WHERE id = $1"
        async with ctx.typing():
            await self.bot.pool.execute(query, playlist["id"])
            del self.bot.cache.playlists[playlist["id"]]
        await ctx.send(f"Deleted playlist named {playlist["name"]}.")

    @playlist.command(name="edit")
    @core.describe(
        playlist="The playlist to edit.", name="The new name for the playlist", image="The new image for the playlist."
    )
    async def playlist_edit(self, ctx: PlayerContext, playlist: Playlist, name: str | None = None, image: str = ""):
        """Edit an existing playlist."""
        message: discord.Message | None = None
        if not name:
            message, name, image = await self.send_playlist_modal(ctx=ctx, playlist=playlist)

        if image:
            res = parse.urlparse(image)
            if not all([res.scheme, res.netloc]):
                raise commands.BadArgument("Image URL provided is invalid.")

        if name == playlist["name"] and image == playlist["image"]:

            if message:
                return await message.edit(content="Playlist was not edited.", view=None)
            return await ctx.send("Playlist was not edited.")

        query = """
            UPDATE playlists
            SET name = $1, image = $2
            WHERE id = $3
        """
        await self.bot.pool.execute(query, name, image, playlist["id"])
        self.bot.cache.playlists[playlist["id"]].update({"name": name, "image": image})
        if message:
            return await message.edit(content="Edited playlist.", view=None)
        return await ctx.send("Edited playlist.")

    @playlist_play.autocomplete("playlist")
    @playlist_songs_add.autocomplete("playlist")
    @playlist_songs_remove.autocomplete("playlist")
    @playlist_delete.autocomplete("playlist")
    @playlist.autocomplete("playlist")
    @playlist_edit.autocomplete("playlist")
    async def playlist_autocomplete(self, itn: Interaction, current: str) -> list[app_commands.Choice[str]]:
        choices = []
        playlists = {
            playlist["name"].lower(): playlist
            for playlist in itn.client.cache.playlists.values()
            if playlist["author"] == itn.user.id
        }
        matches = process.extract(current.lower(), playlists.keys(), limit=25)
        for match in matches:
            name, _, _ = match
            playlist = playlists[name]
            choices.append(app_commands.Choice(name=playlist["name"], value=str(playlist["id"])))
        return choices[:25]

    @core.group()
    async def player(self, ctx: PlayerContext):
        """
        Music player commands.
        """
        await ctx.send_help(ctx.command)

    @player.group(name="dj")
    async def player_dj(self, ctx: PlayerContext):
        """DJ settings commands."""
        await ctx.send_help(ctx.command)

    @player_dj.command(name="enable")
    @core.has_guild_permissions(manage_guild=True)
    async def player_dj_enable(self, ctx: PlayerContext):
        """Enables DJ."""
        vc = ctx.voice_client
        settings = self.bot.cache.player_settings[ctx.guild.id]
        if settings["dj_enabled"] is True:
            return await ctx.send("DJ is already enabled.")

        query = """
            UPDATE player_settings
            SET dj_enabled=$1
            WHERE guild_id=$2
            RETURNING *
        """
        settings = await ctx.bot.pool.fetchrow(query, True, ctx.guild.id)
        self.bot.cache.player_settings[ctx.guild.id] = settings
        if vc:
            vc.dj_enabled = True
        return await ctx.send("Enabled DJ.")

    @player_dj.command(name="disable")
    @core.has_guild_permissions(manage_guild=True)
    async def player_dj_disable(self, ctx: PlayerContext):
        """Disables DJ."""
        vc = ctx.voice_client
        settings = self.bot.cache.player_settings[ctx.guild.id]
        if settings["dj_enabled"] is False:
            return await ctx.send("DJ is already disabled.")

        query = """
            UPDATE player_settings
            SET dj_enabled=$1
            WHERE guild_id=$2
            RETURNING *
        """
        settings = await ctx.bot.pool.fetchrow(query, False, ctx.guild.id)
        self.bot.cache.player_settings[ctx.guild.id] = settings
        if vc:
            vc.dj_enabled = False
        return await ctx.send("Disabled DJ.")

    @player_dj.command(name="role")
    @core.has_guild_permissions(manage_guild=True)
    @core.describe(role="The role to set as DJ")
    async def player_dj_role(self, ctx: PlayerContext, role: discord.Role | None):
        """Sets the DJ role. If not set, the DJ is whoever calls Oi into the channel first."""
        vc = ctx.voice_client
        settings = self.bot.cache.player_settings[ctx.guild.id]
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
        self.bot.cache.player_settings[ctx.guild.id] = settings
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
                await vc.ctx.send(f"{ctx.author} moved the controller to {ctx.channel.mention}", no_tips=True)
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
        """Options on looping."""
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
        """Change the volume of the player."""
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
        """Enable or disable autoplay in this session."""
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
        """Change the speed of the player."""
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
        """Change the pitch of the player."""
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
        """Change the Speed and the Pitch of the player."""
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
        """Adds a termolo effect to the player."""
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
        """Adds a vibrato effect to the player."""
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
        """Adds an effect that will try to remove vocals from the music."""
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
        """Allows only low frequencies to pass through."""
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
        """Creates a rotation effect in the player."""
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
        """Removes all the filters."""
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
        text: Range[str, 1, 500],
        voice: str = "Carter",
        translate: bool = False,
        speed: Range[float, 0.5, 10.0] = 1.0,
    ):
        """Text to speech in voice channel."""
        vc = ctx.voice_client

        if vc.current and not vc.paused:
            return await ctx.send("This command requires the player to be idle.", ephemeral=True)

        current = None
        start = 0
        if vc.current:
            current = vc.current
            start = vc.position

        text = parse.quote(text)

        search = await wavelink.Playable.search(
            f"ftts://{text}?voice={voice}&translate={str(translate).lower()}&speed={speed}", source=None
        )
        if not search:
            return await ctx.send("Could not load speech.", ephemeral=True)

        track = search[0]
        track.extras = Extras(
            requester=str(ctx.author),
            requester_id=ctx.author.id,
            duration=format_seconds(track.length),
            hyperlink="TTS query",
        )

        if ctx.interaction:
            await ctx.send("Sent TTS query to player.", ephemeral=True)

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
            raise commands.BadArgument("No results found matching your search.")
        lyrics = lyrics_data["text"]
        pag = commands.Paginator(max_size=320)
        for line in lyrics.splitlines():
            pag.add_line(line)

        source = LyricPageSource(title, pag)
        paginator = Paginator(source, ctx=ctx, delete_message_after=True)
        await paginator.start()
