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

import contextlib
import copy
import math
from typing import Any, Callable, TYPE_CHECKING, TypeVar

import discord
from discord import ButtonStyle, ui, utils
from discord.ext import menus
from wavelink import AutoPlayMode, Playable, QueueEmpty, QueueMode

from core import ui as cui
from utils import format_seconds, LayoutPaginator, OiView

from .utils import hyperlink_song

if TYPE_CHECKING:
    from discord import Emoji, Interaction, PartialEmoji
    from discord.ui.item import ContainedItemCallbackType as ItemCallbackType

    from utils import Playlist, PlaylistSong

    from .player import Player
    from .types import PlayerContext

S_co = TypeVar("S_co", bound="ui.ActionRow | ui.LayoutView", covariant=True)
BT = TypeVar("BT", bound=ui.Button)


__all__ = (
    "LyricPageSource",
    "PlayerController",
    "QueuePageSource",
)


class PlayerButton(ui.Button["PlayerController"]):
    def __init__(
        self,
        *,
        style: ButtonStyle = ButtonStyle.primary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | Emoji | PartialEmoji | None = None,
        row: int | None = None,
        id: int | None = None,
    ):
        super().__init__(
            style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, row=row, id=id
        )

    async def interaction_check(self, itn: discord.Interaction) -> bool:
        assert self.view is not None
        vc: Player = self.view.vc
        if vc is None or (vc and vc.locked) or not vc.connected or vc.current is None:
            await itn.response.defer()
            return False
        vc = self.view.vc
        if itn.user not in vc.channel.members:
            await itn.response.send_message(f"You need to be in {vc.channel.mention} to use this.", ephemeral=True)
            return False

        assert isinstance(itn.user, discord.Member)

        if not vc.dj_enabled or itn.user.guild_permissions.manage_guild:
            return True

        if vc.dj_role:
            if vc.dj_role in itn.user.roles:
                return True
            await itn.response.send_message(
                f"You need to have {vc.dj_role.mention} role or have `Manage Server` permission to do this.", ephemeral=True
            )
            return False
        if not vc.dj_role:
            if vc.manager and vc.manager == itn.user:
                return True
            await itn.response.send_message(
                "You need to be DJ or have `Manage Server` permission to do this.", ephemeral=True
            )
            return False
        await itn.response.send_message("You need to be a DJ to use this.", ephemeral=True)
        return False


class PlayerSkipButton(PlayerButton):
    async def interaction_check(self, itn: Interaction) -> bool:
        assert self.view is not None
        vc = self.view.vc

        if not vc or (vc and vc.locked) or not vc.current or not vc.connected:
            await itn.response.defer()
            return False

        if itn.user not in vc.channel.members:
            await itn.response.send_message(f"You need to be in {vc.channel.mention} to use this.", ephemeral=True)
            return False
        return True


class PlayerPublicButton(PlayerButton):
    async def interaction_check(self, itn: Interaction) -> bool:
        assert self.view is not None
        vc = self.view.vc

        if not vc or (vc and vc.locked) or not vc.connected:
            await itn.response.defer()
            return False

        return True


class LoopTypeSelect(ui.Select["PlayerController"]):
    def __init__(self, vc: Player):
        self.vc = vc
        self.controller = vc.controller
        vc = self.vc
        assert vc.current is not None
        super().__init__(
            placeholder="Choose loop type...",
            options=[
                discord.SelectOption(
                    emoji="<:loop_one:1294459971014230016>",
                    label=f"Loop {vc.current.title if len(vc.current.title) <= 92 else f'{vc.current.title[:92]}...'}",
                    description="Enable loop for this track only.",
                    value="TRACK",
                ),
                discord.SelectOption(
                    emoji="<:loop_all:1294459877447696385>",
                    label="Loop the Queue",
                    description="Enable loop on the whole queue.",
                    value="QUEUE",
                ),
                discord.SelectOption(
                    emoji="<:stop:1294459644722282577>",
                    label="Disable Loop",
                    description="Disable looping.",
                    value="DISABLE",
                ),
            ],
        )

    async def callback(self, itn: Interaction) -> Any:
        assert self.view is not None
        assert self.controller is not None

        if not self.values:
            await itn.response.defer()
        else:
            command_usage = self.view.command_usage
            disable = self.values[0] == "DISABLE"
            loop_queue = self.values[0] == "QUEUE"

            loop_button = self.controller.loop
            loop_button.emoji = "<:loop_all:1294459877447696385>" if loop_queue else "<:loop_one:1294459971014230016>"
            loop_button.style = discord.ButtonStyle.green
            if disable:
                self.vc.queue.mode = QueueMode.normal
                command_usage(itn, "player loop", mode="off")
            elif loop_queue:
                self.vc.queue.mode = QueueMode.loop_all
                command_usage(itn, "queue loop")
            else:
                self.vc.queue.mode = QueueMode.loop
                command_usage(itn, "player loop", mode="track")

            action_loop = self.controller.action_loop

            action_loop.remove_item(self)
            self.controller.container.remove_item(self.controller.action_loop)
            self.controller.loop_select = None
            await self.controller.update(itn)


source_map = {
    "youtube": "YouTube",
    "you tube": "YouTube",
    "youtube music": "YouTube Music",
    "you tube music": "YouTube Music",
    "spotify": "Spotify",
    "soundcloud": "SoundCloud",
    "sound cloud": "SoundCloud",
    "applemusic": "Apple Music",
    "apple music": "Apple Music",
    "deezer": "Deezer",
}


class EnqueueModal(ui.Modal):
    query = ui.TextInput(
        label="Enter a song:",
        placeholder="Search query or URL",
        style=discord.TextStyle.short,
    )
    source = ui.TextInput(label="Source (Ignore if using URL):", placeholder="Spotify")

    def __init__(self, controller: PlayerController):
        self.controller = controller
        self.vc = controller.vc
        self.source.default = self.vc.ctx.cog.default_source
        super().__init__(title="Enqueue")

    async def on_submit(self, itn: Interaction):
        await itn.response.defer(thinking=True, ephemeral=True)
        vc = self.vc
        cog = vc.ctx.cog

        source = source_map.get(self.source.value.lower(), cog.default_source)
        tracks = await self.vc.fetch_tracks(self.query.value, source)  # type: ignore
        kwargs = {"query": self.query.value}
        if source != cog.default_source:
            kwargs["source"] = source
        self.controller.command_usage(itn, "play", **kwargs)
        if not tracks:
            if self.query.value.startswith(("https://", "http://")):
                not_found = (
                    "No tracks found matching the provided URL.\n"
                    "-# Make sure your URL is valid or try using a different URL."
                )
            else:
                not_found = (
                    f"No tracks found on {source} matching the query: {self.query.value}.\n"
                    "-# Try changing the source, or check your spelling."
                )
            return await itn.followup.send(not_found)
        assert isinstance(itn.user, discord.Member)
        embed = vc.enqueue_tracks(tracks, requester=itn.user)
        assert embed.description is not None
        description = embed.description
        embed.description = description.replace("Added", f"{itn.user} added")
        embed.color = 0x00FFB3
        await vc.ctx.send(embed=embed)
        msg = await itn.followup.send(description, wait=True)
        return await msg.delete(delay=10)


class ControllerAction(ui.ActionRow["PlayerController"]):
    def button(
        self,
        *,
        cls: type[BT] = ui.Button,
        label: str | None = None,
        custom_id: str | None = None,
        disabled: bool = False,
        style: ButtonStyle = ButtonStyle.secondary,
        emoji: str | Emoji | PartialEmoji | None = None,
        id: int | None = None,
    ) -> Callable[[ItemCallbackType[S_co, BT]], BT]:

        def decorator(func: ItemCallbackType[S_co, BT]) -> ItemCallbackType[S_co, BT]:
            ret = cui.button(
                cls=cls,
                label=label,
                custom_id=custom_id,
                disabled=disabled,
                style=style,
                emoji=emoji,
                row=None,
                id=id,
            )(func)
            ret.__discord_ui_parent__ = self  # type: ignore
            return ret  # type: ignore

        return decorator  # type: ignore


class ControllerContainer(ui.Container["PlayerController"]):
    now_playing: ui.Section[PlayerController] = ui.Section(*(ui.TextDisplay("### Now Playing"),), accessory=ui.Thumbnail(""))
    up_next_title: ui.TextDisplay[PlayerController] = ui.TextDisplay("**Up Next**")
    up_next: ui.TextDisplay[PlayerController] = ui.TextDisplay("Nothing")
    queue_length: ui.TextDisplay[PlayerController] = ui.TextDisplay("0")

    def __init__(self, /, *, vc: Player) -> None:
        self.ctx: PlayerContext = vc.ctx
        self.vc: Player = vc

        self.now_playing = ui.Section(*["\u200b"], accessory=ui.Thumbnail(""))
        self.up_next_title = ui.TextDisplay("**Up Next**")
        self.up_next = ui.TextDisplay("\u200b")
        self.separator = ui.Separator(spacing=discord.SeparatorSize.large)

        super().__init__(accent_color=0x00FFB3)

        self.update_ui()

    def update_ui(self, track: Playable | None = None) -> None:
        ctx = self.ctx
        vc = self.vc

        self.now_playing.clear_items()
        self.now_playing.add_item("### Now Playing")

        placeholder_thumb = ctx.guild.icon.url if ctx.guild.icon else ctx.me.display_avatar.url
        # TODO: CHANGE TO OI EMOJI!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        nothing_in_queue = f"Add some songs using <:TODO:1369174874525929483> or {ctx.cog.play.mention}."
        copy_queue = list(vc.queue)
        tng = copy_queue[:2] if vc.queue.mode is QueueMode.loop else copy_queue[:3]
        next_tracks = [f"> {tk.extras.hyperlink} | `{tk.extras.duration}` | {tk.extras.requester}" for tk in tng]
        duration = format_seconds((sum(song.length for song in copy_queue) / 1000), friendly=True)

        if vc.autoplay is not AutoPlayMode.disabled:
            nothing_in_queue = (
                f"Autoplay is enabled. Songs will continue playing, even with an empty queue.\n{nothing_in_queue}"
            )

        joined = "\n".join(next_tracks) or nothing_in_queue

        if track is None:
            self.now_playing.add_item(ui.TextDisplay("[Nothing!](https://www.youtube.com/watch?v=dQw4w9WgXcQ)"))
            self.now_playing.accessory = ui.Thumbnail(placeholder_thumb)
            self.up_next.content = nothing_in_queue

        if track:
            self.now_playing.add_item(ui.TextDisplay(f"{track.extras.hyperlink} | {track.extras.requester}"))
            self.now_playing.add_item(
                ui.TextDisplay(
                    f"Position: `{format_seconds(self.vc.position / 1000)}/{track.extras.duration}`\n"
                    f"Volume: `{self.vc.volume}%`",
                )
            )
            self.now_playing.accessory = ui.Thumbnail(track.artwork or placeholder_thumb)

        if vc.queue.mode is QueueMode.loop:
            loop_track = vc.queue.get()
            joined = (
                f"> [[Looping] {loop_track.title}]({loop_track.uri}) |"
                f" `{loop_track.extras.duration}` | {loop_track.extras.requester}\n{joined}"
            )

        self.up_next.content = joined

        self.queue_length.content = f"-# {len(copy_queue)} tracks in queue ({duration})"


class PlayerController(ui.LayoutView):
    separator: ui.Separator = ui.Separator(spacing=discord.SeparatorSize.small)
    action_one = ControllerAction()
    action_two = ControllerAction()
    action_loop: ui.ActionRow = ui.ActionRow()

    def __init__(self, /, *, vc: Player) -> None:
        self.ctx: PlayerContext = vc.ctx
        self.vc: Player = vc
        self.message: discord.Message | None = None
        self.counter: int = -1
        self.is_updating: bool = False
        self.loop_select: LoopTypeSelect | None = None
        self.lyrics_paginators: dict[int, LayoutPaginator] = {}
        self.container: ControllerContainer = ControllerContainer(vc=vc)

        super().__init__(timeout=None)

        self.clear_items()
        self.add_item(self.container)

    @property
    def labels(self) -> int:
        return self.vc.labels

    @labels.setter
    def labels(self, state: int) -> None:
        self.vc.labels = state

    async def disable(self) -> None:
        self.stop()
        self.set_actions_visible(False)
        self.vc.controller = None
        if self.message is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await self.message.edit(view=self)

    def set_actions_disabled(self, disabled: bool) -> None:
        for item in self.walk_children():
            if isinstance(item, (PlayerButton, LoopTypeSelect)):
                item.disabled = disabled
        self.enqueue.disabled = False

    def set_actions_labels(self) -> None:
        vc = self.vc

        if self.labels == 2:
            self.rewind.label = "Rewind"
            self.pause.label = "Resume" if vc.paused else "Pause"
            self.skip.label = "Skip"
            self.shuffle.label = "Shuffle"
            if vc.queue.mode is QueueMode.normal:
                self.loop.label = "Loop"
            elif vc.queue.mode is QueueMode.loop:
                self.loop.label = "Looping One"
            elif vc.queue.mode is QueueMode.loop_all:
                self.loop.label = "Looping Queue"
            self.autoplay.label = "Autoplay"
            self.lyrics.label = "Lyrics"
            self.enqueue.label = "Enqueue"
        elif self.labels == 1:
            for item in self.walk_children():
                if isinstance(item, PlayerButton) and item.label is not None:
                    item.label = None

    def set_actions_visible(self, visible: bool = True) -> None:
        self.container.remove_item(self.separator)
        self.container.remove_item(self.action_one)
        self.container.remove_item(self.action_two)
        self.container.remove_item(self.action_loop)

        if visible:
            self.container.add_item(self.separator)
            self.container.add_item(self.action_one)
            self.container.add_item(self.action_two)
            if self.action_loop.children:
                self.container.add_item(self.action_loop)

    def update_actions(self) -> None:
        if self.labels == 0:
            self.set_actions_visible(False)
            return

        self.set_actions_visible()
        self.set_actions_labels()
        self.set_actions_disabled(False)

        self.pause.style = ButtonStyle.gray
        self.loop.style = ButtonStyle.gray
        self.autoplay.style = ButtonStyle.gray
        self.loop.emoji = "<:loop_all:1294459877447696385>"

        vc = self.vc

        if vc.queue.mode is not QueueMode.normal:
            self.loop.style = ButtonStyle.green
            if vc.queue.mode == QueueMode.loop:
                self.loop.emoji = "<:loop_one:1294459971014230016>"

        if vc.autoplay is not AutoPlayMode.disabled:
            self.autoplay.style = ButtonStyle.green

        if vc.paused:
            self.pause.style = ButtonStyle.red

        if len(vc.queue) <= 1:
            self.shuffle.disabled = True

        if vc.current is None:
            self.set_actions_disabled(True)

    async def update(self, itn: Interaction | None = None, /, *, invoke: bool = True) -> None:
        if self.is_updating or self.is_finished() or self.message is None:
            return

        self.is_updating = True

        if (itn and itn.is_expired()) or (itn and itn.response.is_done()):
            itn = None

        if not itn and type(self.message) is not discord.Message:
            try:
                self.message = await self.message.fetch()
            except discord.NotFound:
                self.message = None
                return

        edit = itn.response.edit_message if itn and not itn.response.is_done() else self.message.edit
        current = self.vc.current

        if self.counter >= 10:
            self.set_actions_visible(False)
            await edit(view=self)
            if invoke:
                self.message = None
                self.counter = -1
                await self.vc.invoke_controller(current)
                self.is_updating = False
                return
            self.is_updating = False
            return

        self.update_actions()
        self.container.update_ui(current)
        await edit(view=self)

        self.is_updating = False

    def is_manager(self, itn: Interaction) -> tuple[bool, str | None]:

        vc = self.vc

        assert isinstance(itn.user, discord.Member)

        if not vc.dj_enabled or itn.user.guild_permissions.manage_guild:
            return True, None

        if vc.dj_role:
            return (
                vc.dj_role in itn.user.roles,
                f"You need to have {vc.dj_role.mention} or have `Manage Server` permissions to do this.",
            )
        if not vc.dj_role:
            return vc.manager == itn.user, "You need to be DJ or have `Manage Server` permission to do this."
        return True, None

    def command_usage(self, itn: Interaction, name: str, **kwargs: Any):
        # Using the buttons is equivalent to using the command, so we log it.
        # Since button interactions don't have command data, we do this.
        f_ctx = copy.copy(self.ctx)
        cmd = self.ctx.bot.get_command(name)
        if not cmd or not isinstance(itn.user, discord.Member):
            return

        f_ctx.command = cmd
        f_ctx.author = itn.user
        # We do this so that arguemnts that were "used" show up when logged.
        itn.namespace.__dict__.update(kwargs)
        f_ctx.interaction = itn
        self.ctx.bot.dispatch("command", f_ctx)

    @action_one.button(cls=PlayerButton, emoji="<:skip_left:1294459900696461364>")
    async def rewind(self, itn: Interaction, _: PlayerButton):
        await self.vc.seek(0)
        if self.vc.paused:
            await self.vc.pause(False)
        self.command_usage(itn, "seek", time="0:00")
        await self.update(itn)

    @action_one.button(cls=PlayerButton, emoji="<:play_or_pause:1294459947572138069>")
    async def pause(self, itn: Interaction, _: PlayerButton):
        await self.vc.pause(not self.vc.paused)
        self.command_usage(itn, "resume" if not self.vc.paused else "pause")
        await self.update(itn)

    @action_one.button(cls=PlayerSkipButton, emoji="<:skip_right:1294459785130934293>")
    async def skip(self, itn: Interaction, _: PlayerSkipButton):
        vc = self.vc

        assert self.vc.current is not None
        assert isinstance(itn.user, discord.Member)

        send = itn.followup.send if itn.response.is_done() else itn.response.send_message

        is_manager, __ = self.is_manager(itn)
        if is_manager:
            await self.vc.skip()
            await send(f"{itn.user} has skipped the track.")
        elif self.vc.current.extras.requester_id == itn.user.id:
            await self.vc.skip()
            await send(f"Track requester {itn.user} has skipped the track.")
        else:
            required = math.ceil(len(vc.channel.members) / 2)
            if itn.user.id in self.vc.skip_votes:
                await send("You already voted to skip the track.", ephemeral=True)
                return
            self.vc.skip_votes.add(itn.user.id)
            if len(self.vc.skip_votes) >= required:
                await self.vc.skip()
                await send(f"Vote to skip passed ({required} of {required}). Skipping.")
                return
            await send(f"Voted to skip. ({len(self.vc.skip_votes)}/{required})", ephemeral=True)
        self.command_usage(itn, "skip")
        await self.update(itn, invoke=False)

    @action_one.button(cls=PlayerButton, emoji="<:autoplay:1294460017348710420>")
    async def autoplay(self, itn: Interaction, _: PlayerButton):
        state = AutoPlayMode.disabled if self.vc.autoplay == AutoPlayMode.enabled else AutoPlayMode.enabled
        self.vc.autoplay = state
        self.command_usage(itn, "player autoplay", state=not bool(state.value))
        await self.update(itn)

    @action_two.button(cls=PlayerPublicButton, emoji="<:queue_add:1310474338868138004>")
    async def enqueue(self, itn: Interaction, _: PlayerPublicButton):
        if itn.user not in self.vc.channel.members:
            await itn.response.send_message(
                f"You need to be in {self.vc.channel.mention} to add songs to the queue.", ephemeral=True
            )
            return
        modal = EnqueueModal(self)
        await itn.response.send_modal(modal)
        await modal.wait()

        if not self.vc.current:
            try:
                await self.vc.play(self.vc.queue.get())
            except QueueEmpty:
                pass
            else:
                return

        await self.update(itn)

    @action_two.button(cls=PlayerButton, emoji="<:shuffle:1294459691119935600>")
    async def shuffle(self, itn: Interaction, _: PlayerButton):
        vc = self.vc

        vc.queue.shuffle()
        self.command_usage(itn, "queue shuffle")
        await self.update(itn)

    @action_two.button(cls=PlayerButton, emoji="<:loop_all:1294459877447696385>")
    async def loop(self, itn: Interaction, _: PlayerButton):
        assert self.vc.current is not None

        if not self.loop_select:
            new_select = LoopTypeSelect(self.vc)
            self.loop_select = new_select
            self.action_loop.add_item(new_select)
            self.container.add_item(self.action_loop)
        else:
            self.action_loop.remove_item(self.loop_select)
            self.container.remove_item(self.action_loop)
            self.loop_select = None

        await self.update(itn)

    @action_two.button(cls=PlayerPublicButton, emoji="<:lyrics:1297669978635505675>")
    async def lyrics(self, itn: Interaction, _: PlayerPublicButton):

        if self.vc.current is None:
            return await itn.response.defer()

        self.command_usage(itn, "lyrics", search=self.vc.current.title)

        if itn.user.id in self.lyrics_paginators:
            paginator = self.lyrics_paginators[itn.user.id]
            assert isinstance(paginator.source, LyricPageSource)

            if paginator.message:
                with contextlib.suppress(discord.NotFound):
                    await paginator.message.delete()
            paginator.stop()
            del self.lyrics_paginators[itn.user.id]

        await itn.response.defer(thinking=True, ephemeral=True)
        lyrics_data = await self.vc.fetch_current_lyrics()
        if not lyrics_data or (lyrics_data and not lyrics_data["text"]):
            await itn.followup.send("Could not find lyrics.", ephemeral=True)
            return None
        lyrics = lyrics_data["text"]

        chunked_lyrics = []

        for chunk in utils.as_chunks(lyrics.splitlines(), 8):
            joined = "\n".join(chunk)

            if len(joined) > 3000:
                # If for whatever reason that the lyrics exceed 3500 characters,
                # (very unlikely) we just truncate it here. We leave some space for
                # the title, hence 3500, not 4000.
                chunked_lyrics.append(f"{joined[:3497]}...")
            else:
                chunked_lyrics.append(joined)

        paginator = LyricsPaginator(
            LyricPageSource(self.vc.current.title, chunked_lyrics),
            ctx=self.ctx,
            delete_message_after=True,
            timeout=((self.vc.current.length / 1000) * 2),
            nav_in_container=True,
        )  # Double the track's length

        await paginator.start(itn)
        self.lyrics_paginators[itn.user.id] = paginator
        return None


class QueuePageSource(menus.ListPageSource):
    def __init__(self, player: Player) -> None:
        self.vc = player
        super().__init__(entries=list(enumerate(list(player.queue), start=1)), per_page=8)

    async def format_page(self, _: menus.Menu, tracks: list[tuple[int, Playable]]) -> ui.Container:
        ctx = self.vc.ctx

        url = discord.PartialEmoji(name="music_note", id=1368398933696450620).url
        container = ui.Container(accent_color=0x00FFB3)
        section = ui.Section(
            *[f"### Up Next in {ctx.guild.name}"],
            accessory=ui.Thumbnail(url),
        )

        if ctx.guild.icon:
            section.accessory = ui.Thumbnail(ctx.guild.icon.url)
        up_next = ""
        for count, track in tracks:
            if len(track._title) > 90:
                track._title = f"{track._title[:50]}..."
                track.extras.hyperlink = f"[{track.title}]({track.uri})"
            up_next = f"{up_next}\n{count}. {track.extras.hyperlink} | {track.extras.requester}"
        section.add_item(up_next)
        container.add_item(section)

        return container


class PlaylistPageSource(menus.ListPageSource):
    def __init__(self, playlist: Playlist) -> None:
        self.playlist: Playlist = playlist
        self.songs: dict[int, PlaylistSong] = self.playlist["songs"]
        super().__init__(list(self.songs.keys()), per_page=8)

    async def format_page(self, _: menus.Menu, playlist_ids: list[int]) -> ui.Container:
        lines = []

        for p_id in playlist_ids:
            song = self.songs[p_id]
            if len(song["title"]) > 90:
                song["title"] = f"{song["title"][: len(song["artist"])]}..."
            lines.append(f"{song["position"]}. {hyperlink_song(song)} - {song["artist"]}")

        image = self.playlist.get("image")
        accessory = ui.Thumbnail(image) if image else ui.Button(label="No Image", disabled=True)
        return ui.Container(
            *[
                ui.Section(
                    *[
                        f"### Playlist Info: {self.playlist["name"]}",
                        "\n".join(lines),
                        f"-# {len(self.songs)} songs in {self.playlist["name"]}",
                    ],
                    accessory=accessory,
                )
            ],
            accent_color=0x00FFB3,
        )


class LyricPageSource(menus.ListPageSource):
    def __init__(self, title: str, paginator: list[str]):
        self.title = title
        super().__init__(paginator, per_page=1)

    async def format_page(self, _: menus.MenuPages, page: str) -> ui.Container:
        return ui.Container(*[ui.TextDisplay(f"### {self.title} lyrics\n{page}")], accent_color=0x00FFB3)


class LyricsPaginator(LayoutPaginator):
    async def interaction_check(self, _: Interaction):
        # All instances of this paginator are sent ephemerally
        return True

    async def start(self, itn: Interaction):
        await self.source._prepare_once()
        page = await self.source.get_page(self.current_page)
        await self.update_view(page)
        await self.update_navigation(self.current_page)

        if itn.response.is_done():
            msg = await itn.followup.send(view=self, wait=True)
        else:
            await itn.response.send_message(view=self, ephemeral=True)
            msg = await itn.original_response()

        self.message = msg


class PlaylistInfoModal(ui.Modal):
    playlist = discord.ui.TextInput(
        label="Enter a name",
        style=discord.TextStyle.short,
        placeholder="My Playlist",
        required=True,
        min_length=1,
        max_length=100,
    )
    image = discord.ui.TextInput(
        label="Enter an image URL",
        style=discord.TextStyle.short,
        required=False,
    )

    def __init__(self, title: str, *, name: str | None = None, image: str | None = None) -> None:
        self.name: str
        self.url: str | None = None

        self.playlist.default = name
        self.image.default = image
        super().__init__(title=title)

    async def on_submit(self, itn: Interaction) -> None:
        await itn.response.defer()
        self.name = self.playlist.value
        self.url = self.image.value


class PlaylistModalView(OiView):
    def __init__(
        self, *, title: str, playlist: Playlist | None = None, members: list[discord.Member | discord.User], timeout=180
    ):
        self.title: str = title
        self.playlist: Playlist | None = playlist
        self.name: str = ""
        self.url: str | None = None
        if playlist:
            self.name = playlist["name"]
            self.url = playlist["image"]

        super().__init__(members=members, timeout=timeout)
        self.open_modal.label = title

    async def on_timeout(self):
        if self.message and not self.name:
            self.open_modal.disabled = True
            await self.message.edit(content="Timed out.", view=self)

    @ui.button(style=discord.ButtonStyle.green)
    async def open_modal(self, itn: Interaction, button: ui.Button) -> None:
        name = self.playlist["name"] if self.playlist else None
        image = self.playlist.get("image") if self.playlist else None
        modal = PlaylistInfoModal(self.title, name=name, image=image)
        await itn.response.send_modal(modal)
        await modal.wait()
        self.name = modal.name
        self.url = modal.url
        self.stop()
