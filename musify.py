# Discord Music Bot with Interactive Buttons (No Reactions) — Full, Fixed Code
# Requires: discord.py v2+, yt-dlp, ffmpeg installed and in PATH
# pip install -U discord.py yt-dlp

import asyncio
from collections import deque
from dataclasses import dataclass, field
import os
import socket
from typing import Deque, Optional
import threading

import discord
from discord.ext import commands
from discord.ui import View, button
import yt_dlp
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# Bot Setup
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# yt-dlp & FFmpeg configuration
# -----------------------------
YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "default_search": "ytsearch",
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "preferredquality": "192",
    "socket_timeout": 10,  # yt-dlp socket timeout
    "http_timeout": 10,    # yt-dlp HTTP timeout
}
FFMPEG_BEFORE = "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rw_timeout 10000000"
FFMPEG_OPTS = "-vn -timeout 10"

YTDL = yt_dlp.YoutubeDL(YTDL_OPTS)

# -----------------------------
# Data structures per guild
# -----------------------------
@dataclass
class Track:
    url: str
    title: str
    webpage_url: str
    duration: Optional[int] = 0
    thumbnail: Optional[str] = None


@dataclass
class GuildMusic:
    guild_id: int
    queue: Deque[Track] = field(default_factory=deque)
    looping: bool = False
    current: Optional[Track] = None
    volume: float = 0.5  # 0.0–2.0
    message: Optional[discord.Message] = None  # the now-playing message with buttons
    last_channel_id: Optional[int] = None

    def toggle_loop(self) -> bool:
        self.looping = not self.looping
        return self.looping


STATE: dict[int, GuildMusic] = {}

# -----------------------------
# Helpers
# -----------------------------
async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError("You must be connected to a voice channel.")
    vc = ctx.voice_client
    if vc and vc.channel != ctx.author.voice.channel:
        try:
            await vc.move_to(ctx.author.voice.channel)
        except Exception as e:
            await ctx.send(f"❌ Failed to move to voice channel: `{e}`")
            raise commands.CommandError("Failed to move to voice channel.")
    if not vc:
        try:
            # Set a timeout for connection (default 15s, can be adjusted)
            vc = await ctx.author.voice.channel.connect(timeout=15)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await ctx.send("❌ Timed out connecting to voice. Please try again or check your network/region settings.")
            raise commands.CommandError("Voice connection timed out.")
        except Exception as e:
            await ctx.send(f"❌ Failed to connect to voice channel: `{e}`")
            raise commands.CommandError("Failed to connect to voice channel.")
    return vc


def ytdl_search(query: str) -> Track:
    try:
        # Set a timeout for all socket operations (yt-dlp uses urllib/request)
        socket.setdefaulttimeout(10)
        info = YTDL.extract_info(query, download=False)
    except Exception as e:
        raise RuntimeError(f"yt-dlp error: {e}")
    if info is None:
        raise RuntimeError("No results from yt-dlp.")
    if "entries" in info:
        info = next((e for e in info["entries"] if e), None)
        if info is None:
            raise RuntimeError("No playable entry found.")
    return Track(
        url=info.get("url") or info.get("formats", [{}])[0].get("url", ""),
        title=info.get("title", "Unknown Title"),
        webpage_url=info.get("webpage_url", ""),
        duration=info.get("duration", 0),
        thumbnail=info.get("thumbnail"),
    )


def build_embed(track: Track) -> discord.Embed:
    minutes = (track.duration or 0) // 60
    seconds = (track.duration or 0) % 60
    e = discord.Embed(
        title="Now Playing",
        description=f"{track.title}\n\n[Open on YouTube]({track.webpage_url})",
        color=discord.Color.blurple(),
    )
    e.add_field(name="Duration", value=f"{minutes}:{seconds:02d}" if track.duration else "live/unknown")
    if track.thumbnail:
        e.set_thumbnail(url=track.thumbnail)
    return e


async def create_source(track: Track, volume: float) -> discord.PCMVolumeTransformer:
    try:
        src = discord.FFmpegPCMAudio(
            track.url,
            before_options=FFMPEG_BEFORE,
            options=FFMPEG_OPTS,
        )
        return discord.PCMVolumeTransformer(src, volume=volume)
    except Exception as e:
        raise RuntimeError(f"FFmpeg error: {e}")


async def start_playback(ctx: commands.Context, gm: GuildMusic):
    vc = ctx.voice_client
    if not vc:
        vc = await ensure_voice(ctx)

    # If something is already playing, do nothing here
    if vc.is_playing() or vc.is_paused():
        return

    if not gm.queue and not gm.current:
        return

    # If we have a current (loop), otherwise pop next
    if gm.current is None:
        gm.current = gm.queue.popleft()

    try:
        source = await create_source(gm.current, gm.volume)
        def _after_play(err: Optional[Exception]):
            if err:
                print(f"Player error: {err}")
            # schedule next on bot loop
            fut = asyncio.run_coroutine_threadsafe(next_track(ctx, gm), bot.loop)
            try:
                fut.result()
            except Exception as e:
                print("after_play error:", e)
        vc.play(source, after=_after_play)
    except Exception as e:
        print("start_playback error:", e)
        await ctx.send(f"❌ Error playing track: {e}. Skipping to next.")
        await next_track(ctx, gm, skip_current=True)
        return

    # Send/refresh the control panel
    try:
        view = ControlPanel(gm)
        embed = build_embed(gm.current)
        send_new_msg = False
        # Check if old player message is >10 messages old
        if gm.message:
            try:
                # Fetch last 11 messages (including the old player message)
                history = [msg async for msg in gm.message.channel.history(limit=11)]
                # If gm.message is not in the last 10 messages, send new
                if gm.message not in history[:10]:
                    send_new_msg = True
            except Exception:
                send_new_msg = True
        else:
            send_new_msg = True

        if not send_new_msg and gm.message and gm.message.channel.permissions_for(gm.message.channel.guild.me).manage_messages:
            try:
                await gm.message.edit(embed=embed, view=view)
            except Exception:
                gm.message = await ctx.send(embed=embed, view=view)
        else:
            gm.message = await ctx.send(embed=embed, view=view)
    except Exception as e:
        print("panel error:", e)


async def next_track(ctx: commands.Context, gm: GuildMusic, skip_current: bool = False):
    vc = ctx.voice_client
    if not vc:
        return

    if gm.looping and not skip_current and gm.current is not None:
        # requeue the same track at front
        pass  # keep gm.current
    else:
        gm.current = None
        if gm.queue:
            gm.current = gm.queue.popleft()
        else:
            try:
                await vc.disconnect()
            except Exception:
                pass
            return

    await start_playback(ctx, gm)


# -----------------------------
# Control Panel (Buttons)
# -----------------------------
class ControlPanel(View):
    def __init__(self, gm: GuildMusic):
        super().__init__(timeout=None)
        self.gm = gm

    async def _ctx(self, interaction: discord.Interaction) -> commands.Context:
        return await bot.get_context(await interaction.channel.fetch_message(interaction.message.id))

    @button(label="⏮", style=discord.ButtonStyle.primary, custom_id="btn_prev")
    async def previous(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        # simple previous: place current at left, and rotate last item to front if any
        if self.gm.current:
            self.gm.queue.appendleft(self.gm.current)
        if self.gm.queue:
            # rotate last to front to simulate previous
            last = self.gm.queue.pop()
            self.gm.queue.appendleft(last)
        ctx = await bot.get_context(interaction.message)
        await next_track(ctx, self.gm, skip_current=True)

    @button(label="⏯", style=discord.ButtonStyle.secondary, custom_id="btn_toggle")
    async def toggle(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
            elif vc.is_paused():
                vc.resume()

    @button(label="⏭", style=discord.ButtonStyle.primary, custom_id="btn_skip")
    async def skip(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    @button(label="🔁", style=discord.ButtonStyle.success, custom_id="btn_loop")
    async def loop(self, interaction: discord.Interaction, _):
        loop_state = self.gm.toggle_loop()
        await interaction.response.send_message(
            f"Loop is now **{'ON' if loop_state else 'OFF'}**", ephemeral=True
        )

    @button(label="🔀", style=discord.ButtonStyle.secondary, custom_id="btn_shuffle")
    async def shuffle(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        if self.gm.queue:
            import random
            random.shuffle(self.gm.queue)

    @button(label="🔉", style=discord.ButtonStyle.secondary, custom_id="btn_voldown")
    async def voldown(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        self.gm.volume = max(0.0, round(self.gm.volume - 0.1, 2))
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = self.gm.volume

    @button(label="🔊", style=discord.ButtonStyle.secondary, custom_id="btn_volup")
    async def volup(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        self.gm.volume = min(2.0, round(self.gm.volume + 0.1, 2))
        vc = interaction.guild.voice_client
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = self.gm.volume

    @button(label="⏹", style=discord.ButtonStyle.danger, custom_id="btn_stop")
    async def stop(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc:
            self.gm.queue.clear()
            self.gm.current = None
            vc.stop()
            try:
                await vc.disconnect()
            except Exception:
                pass


def search_tracks(query: str, max_results: int = 10) -> list[Track]:
    try:
        socket.setdefaulttimeout(10)
        info = YTDL.extract_info(query, download=False)
    except Exception as e:
        return []
    results = []
    if info is None:
        return results
    # Always treat as a search: if not a playlist, wrap single result as entries
    entries = []
    if "entries" in info and isinstance(info["entries"], list):
        entries = [e for e in info["entries"] if e]
    else:
        # If not a playlist/search, try to simulate search by running ytsearch
        if info.get("webpage_url") and info.get("title"):
            entries = [info]
    for entry in entries[:max_results]:
        results.append(Track(
            url=entry.get("url") or entry.get("formats", [{}])[0].get("url", ""),
            title=entry.get("title", "Unknown Title"),
            webpage_url=entry.get("webpage_url", ""),
            duration=entry.get("duration", 0),
            thumbnail=entry.get("thumbnail"),
        ))
    return results


class SearchPanel(View):
    def __init__(self, tracks: list[Track], ctx: commands.Context, gm: GuildMusic):
        super().__init__(timeout=60)
        self.tracks = tracks
        self.ctx = ctx
        self.gm = gm
        for i, track in enumerate(tracks):
            self.add_item(self.make_button(i, track.title))

    def make_button(self, idx, title):
        return discord.ui.Button(
            label=f"{idx+1}", style=discord.ButtonStyle.primary, custom_id=f"search_{idx}", row=idx//5
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the user who invoked the command to interact
        return interaction.user == self.ctx.author

    async def on_timeout(self):
        try:
            await self.ctx.send("❌ Search timed out.")
        except Exception:
            pass

    async def on_error(self, error, item, interaction):
        await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)

    async def callback(self, interaction: discord.Interaction):
        idx = int(interaction.data["custom_id"].split("_")[1])
        track = self.tracks[idx]
        self.gm.queue.append(track)
        await interaction.response.send_message(f"➕ Queued: **{track.title}**", ephemeral=True)
        await start_playback(self.ctx, self.gm)
        self.stop()

    def add_item(self, button):
        async def button_callback(interaction: discord.Interaction):
            await self.callback(interaction)
        button.callback = button_callback
        super().add_item(button)


# -----------------------------
# Commands
# -----------------------------
@bot.command(name="join")
async def cmd_join(ctx: commands.Context):
    await ensure_voice(ctx)
    await ctx.message.add_reaction("✅")


@bot.command(name="leave")
async def cmd_leave(ctx: commands.Context):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    await ctx.message.add_reaction("👋")


@bot.command(name="play", aliases=["p"])  # !play <url or search>
async def cmd_play(ctx: commands.Context, *, query: str):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    gm.last_channel_id = ctx.channel.id
    await ensure_voice(ctx)

    try:
        track = ytdl_search(query)
    except Exception as e:
        await ctx.reply(f"❌ Failed to fetch audio: `{e}`")
        return

    gm.queue.append(track)
    await ctx.send(f"➕ Queued: **{track.title}**")
    await start_playback(ctx, gm)


@bot.command(name="skip", aliases=["s"]) 
async def cmd_skip(ctx: commands.Context):
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()


@bot.command(name="queue", aliases=["q"]) 
async def cmd_queue(ctx: commands.Context):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    if not gm.queue:
        await ctx.send("Queue is empty.")
        return
    desc = "\n".join([f"`{i+1:2}` • {t.title}" for i, t in enumerate(list(gm.queue)[:15])])
    await ctx.send(embed=discord.Embed(title="Up Next", description=desc))


@bot.command(name="loop")
async def cmd_loop(ctx: commands.Context):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    state = gm.toggle_loop()
    await ctx.send(f"🔁 Loop is now **{'ON' if state else 'OFF'}**")


@bot.command(name="volume", aliases=["vol"])  # !vol 0-200
async def cmd_volume(ctx: commands.Context, percent: int):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    pct = max(0, min(200, percent))
    gm.volume = round(pct / 100.0, 2)
    vc = ctx.voice_client
    if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = gm.volume
    await ctx.send(f"🔈 Volume set to **{pct}%**")


@bot.command(name="search")
async def cmd_search(ctx: commands.Context, *, query: str):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    tracks = search_tracks(query, max_results=10)
    if not tracks:
        await ctx.send("❌ No results found or network error.")
        return
    desc = "\n".join([f"`{i+1}` • [{t.title}]({t.webpage_url})" for i, t in enumerate(tracks)])
    embed = discord.Embed(title="Search Results", description=desc)
    view = SearchPanel(tracks, ctx, gm)
    await ctx.send(embed=embed, view=view)


# -----------------------------
# Startup
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")


def keep_alive():
    from flask import Flask
    app = Flask('')

    @app.route('/')
    def home():
        return "Bot is running!"

    app.run(host='0.0.0.0', port=8080)

# Run the bot
# Put your token in the DISCORD_TOKEN env var or replace below directly.
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in .env file")
threading.Thread(target=keep_alive).start()
bot.run(TOKEN)
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in .env file")
threading.Thread(target=keep_alive).start()
bot.run(TOKEN)
