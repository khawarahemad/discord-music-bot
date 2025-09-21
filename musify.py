# Discord Music Bot — Fixed & Advanced (with Proper Remote Cookie Support)

import asyncio
import logging
import os
import random
import socket
import tempfile
import threading
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, List

import discord
from discord.ext import commands
from discord.ui import View, button
import yt_dlp
from dotenv import load_dotenv

load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("music_bot")

# --- Cookie Handling (Local or Remote) ---

def fetch_cookies_to_tempfile(url: str) -> Optional[str]:
    try:
        logger.info(f"Fetching cookies from URL: {url}")
        resp = urllib.request.urlopen(url, timeout=10)
        content = resp.read().decode("utf-8")
        # Create a temp file
        tmp = tempfile.NamedTemporaryFile(delete=False, mode="w", encoding="utf-8", suffix=".txt")
        tmp.write(content)
        tmp.close()
        logger.info(f"✅ Cookies downloaded to temp file: {tmp.name}")
        return tmp.name
    except Exception as e:
        logger.warning(f"⚠️ Failed to fetch remote cookies: {e}")
        return None

USE_REMOTE_COOKIES = os.getenv("USE_REMOTE_COOKIES", "false").lower() == "true"
COOKIES_URL = os.getenv("YTDLP_COOKIES_URL", "https://raw.githubusercontent.com/khawarahemad/assets/main/cookies.txt")
COOKIES_PATH: Optional[str] = None

if USE_REMOTE_COOKIES:
    # Try to fetch and use remote cookies
    COOKIES_PATH = fetch_cookies_to_tempfile(COOKIES_URL)
    if not COOKIES_PATH:
        logger.warning("Remote cookies enabled but failed to fetch; proceeding without cookies or local fallback.")
else:
    # Try to use local cookies file
    local_path = os.getenv("YTDLP_COOKIES")
    if local_path:
        if os.path.isfile(local_path):
            COOKIES_PATH = local_path
            logger.info(f"✅ Using local cookies file: {COOKIES_PATH}")
        else:
            logger.warning(f"⚠️ Local cookies path does not exist: {local_path}")
    else:
        logger.info("No local cookies path provided; cookies will be None")

# --- yt-dlp / ffmpeg settings ---
YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "default_search": "ytsearch",
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "socket_timeout": 15,
    "http_timeout": 15,
    "cookies": COOKIES_PATH,  # this may be None if no cookie file
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Increase resilience when connecting to streams
FFMPEG_BEFORE = (
    "-nostdin "
    "-reconnect 1 "
    "-reconnect_streamed 1 "
    "-reconnect_delay_max 5 "
    "-rw_timeout 20000000 "  # 20s
    "-probesize 50M "
    "-analyzeduration 100M "
)
FFMPEG_OPTS = "-vn -bufsize 100M"

YTDL = yt_dlp.YoutubeDL(YTDL_OPTS)
MAX_PLAYLIST_ITEMS = int(os.getenv("MAX_PLAYLIST_ITEMS", "50"))

# --- Data structures ---
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
    volume: float = 0.5
    message: Optional[discord.Message] = None
    last_channel_id: Optional[int] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

STATE: dict[int, GuildMusic] = {}

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --- Optional Spotify ---
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    sp = None
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET
            )
        )
        logger.info("Spotify support initialized.")
    else:
        logger.info("Spotify credentials not set; Spotify support disabled.")
except Exception as e:
    sp = None
    logger.warning(f"Spotify support disabled: {e}")

# --- Helpers ---
async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError("You must be connected to a voice channel.")
    vc = ctx.voice_client
    if vc and vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)
    if not vc:
        vc = await ctx.author.voice.channel.connect(timeout=15)
    return vc

async def ytdl_extract(query: str):
    # wrapper for blocking yt-dlp calls
    try:
        socket.setdefaulttimeout(15)
        return await asyncio.to_thread(YTDL.extract_info, query, download=False)
    except Exception:
        logger.exception("yt-dlp extraction failed")
        return None

async def ytdl_search(query: str, ctx: commands.Context = None, gm: GuildMusic = None) -> List[Track]:
    """Search/resolve a query via yt-dlp and append results to gm.queue (if gm provided).
    Returns the list of Track objects discovered (not necessarily queued if gm is None).
    """
    found: List[Track] = []
    try:
        # Spotify special handling
        if "spotify.com" in query and sp:
            try:
                if "playlist" in query:
                    playlist_id = query.split("/")[-1].split("?")[0]
                    items = sp.playlist_items(playlist_id, limit=MAX_PLAYLIST_ITEMS)
                    tracks_info = [i['track'] for i in items['items'] if i.get('track')]
                else:
                    track_id = query.split("/")[-1].split("?")[0]
                    t = sp.track(track_id)
                    tracks_info = [t]
                for t in tracks_info:
                    title = f"{t['name']} by {', '.join([a['name'] for a in t['artists']])}"
                    yt = await ytdl_extract(f"ytsearch1:{title}")
                    if yt:
                        entry = (yt['entries'][0] if 'entries' in yt and yt['entries'] else yt)
                        tr = Track(
                            url=entry.get('url') or entry.get('formats', [{}])[0].get('url', ''),
                            title=entry.get('title', title),
                            webpage_url=entry.get('webpage_url', ''),
                            duration=entry.get('duration', 0),
                            thumbnail=entry.get('thumbnail'),
                        )
                        found.append(tr)
                        if gm:
                            async with gm.lock:
                                gm.queue.append(tr)
                return found
            except Exception:
                logger.exception("Spotify handling failed; falling back to direct yt-dlp search")

        info = await ytdl_extract(query)
        if not info:
            return found

        # playlist / search results
        if isinstance(info, dict) and 'entries' in info and info['entries']:
            entries = [e for e in info['entries'] if e][:MAX_PLAYLIST_ITEMS]
            for entry in entries:
                tr = Track(
                    url=entry.get('url') or entry.get('formats', [{}])[0].get('url', ''),
                    title=entry.get('title', 'Unknown Title'),
                    webpage_url=entry.get('webpage_url', ''),
                    duration=entry.get('duration', 0),
                    thumbnail=entry.get('thumbnail'),
                )
                found.append(tr)
                if gm:
                    async with gm.lock:
                        gm.queue.append(tr)
        else:
            # single video result
            entry = info if isinstance(info, dict) else None
            if entry:
                tr = Track(
                    url=entry.get('url') or entry.get('formats', [{}])[0].get('url', ''),
                    title=entry.get('title', 'Unknown Title'),
                    webpage_url=entry.get('webpage_url', ''),
                    duration=entry.get('duration', 0),
                    thumbnail=entry.get('thumbnail'),
                )
                found.append(tr)
                if gm:
                    async with gm.lock:
                        gm.queue.append(tr)
    except Exception:
        logger.exception("Error in ytdl_search")
    return found

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
    except Exception:
        logger.exception("FFmpeg create_source failed")
        raise

async def start_playback(ctx: Optional[commands.Context], gm: GuildMusic, vc: Optional[discord.VoiceClient] = None):
    """Ensure a track is playing for the guild music. If ctx is provided, it may be used to create a connection.
    vc may be passed in to avoid ctx-based voice lookup.
    """
    try:
        # Determine VoiceClient
        if vc is None:
            if ctx and ctx.voice_client:
                vc = ctx.voice_client
            else:
                guild = bot.get_guild(gm.guild_id)
                vc = guild.voice_client if guild else None

        # If vc is missing and ctx available, try to connect
        if not vc:
            if ctx:
                vc = await ensure_voice(ctx)
            else:
                logger.debug("No VoiceClient available to start playback")
                return

        # If already playing/paused, skip
        if vc.is_playing() or vc.is_paused():
            return

        # Grab next track under lock
        async with gm.lock:
            if gm.current is None:
                if not gm.queue:
                    logger.debug("Queue empty, nothing to play")
                    return
                gm.current = gm.queue.popleft()
            track_to_play = gm.current

        try:
            source = await create_source(track_to_play, gm.volume)

            def _after(err: Optional[Exception]):
                if err:
                    logger.exception(f"Player error: {err}")
                # schedule next_track on the bot loop
                fut = asyncio.run_coroutine_threadsafe(next_track(None, gm), bot.loop)
                try:
                    fut.result()
                except Exception:
                    logger.exception("Failed to schedule next_track from after callback")

            vc.play(source, after=_after)
        except Exception:
            logger.exception("Failed to play track; skipping to next")
            async with gm.lock:
                gm.current = None
            await next_track(ctx, gm, skip_current=True)
            return

        # Build and send/update control panel
        try:
            embed = build_embed(track_to_play)
            view = ControlPanel(gm)
            if gm.message:
                try:
                    await gm.message.edit(embed=embed, view=view)
                except Exception:
                    # fallback to sending new
                    if ctx:
                        gm.message = await ctx.send(embed=embed, view=view)
                    else:
                        ch = bot.get_channel(gm.last_channel_id) if gm.last_channel_id else None
                        if ch:
                            gm.message = await ch.send(embed=embed, view=view)
            else:
                if ctx:
                    gm.message = await ctx.send(embed=embed, view=view)
                else:
                    ch = bot.get_channel(gm.last_channel_id) if gm.last_channel_id else None
                    if ch:
                        gm.message = await ch.send(embed=embed, view=view)
        except Exception:
            logger.exception("Failed to send or edit control panel message")

    except Exception:
        logger.exception("start_playback top-level error")

async def next_track(ctx: Optional[commands.Context], gm: GuildMusic, skip_current: bool = False):
    """Advance to the next track. If skip_current==True, force a skip. ctx optional."""
    guild = bot.get_guild(gm.guild_id)
    vc = guild.voice_client if guild else None
    if not vc:
        logger.debug("next_track: no voice client present")
        return

    async with gm.lock:
        if gm.looping and not skip_current and gm.current:
            # replay same track
            pass
        else:
            if gm.queue:
                gm.current = gm.queue.popleft()
            else:
                gm.current = None
                try:
                    await vc.disconnect()
                except Exception:
                    logger.exception("Failed to disconnect vc when queue empty")
                # Update control message
                if gm.message:
                    try:
                        await gm.message.edit(content="Queue ended.", embed=None, view=None)
                    except Exception:
                        pass
                return

    await start_playback(ctx, gm, vc=vc)

# --- Control panel (buttons) ---
class ControlPanel(View):
    def __init__(self, gm: GuildMusic):
        super().__init__(timeout=None)
        self.gm = gm

    async def _get_vc(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        return interaction.guild.voice_client

    @button(label="⏮", style=discord.ButtonStyle.primary, custom_id="btn_prev")
    async def previous(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        async with self.gm.lock:
            if self.gm.current:
                self.gm.queue.appendleft(self.gm.current)
            if self.gm.queue:
                last = self.gm.queue.pop()
                self.gm.queue.appendleft(last)
            self.gm.current = None
        await next_track(None, self.gm, skip_current=True)
        await interaction.followup.send("⏮ Moved to previous track.", ephemeral=True)

    @button(label="⏯", style=discord.ButtonStyle.secondary, custom_id="btn_toggle")
    async def toggle(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = await self._get_vc(interaction)
        if vc:
            if vc.is_playing():
                vc.pause()
                await interaction.followup.send("⏸ Paused.", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                await interaction.followup.send("▶️ Resumed.", ephemeral=True)
            else:
                await interaction.followup.send("Nothing is playing.", ephemeral=True)

    @button(label="⏭", style=discord.ButtonStyle.primary, custom_id="btn_skip")
    async def skip(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = await self._get_vc(interaction)
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.followup.send("⏭ Skipped.", ephemeral=True)
        else:
            await interaction.followup.send("Nothing to skip.", ephemeral=True)

    @button(label="🔁", style=discord.ButtonStyle.success, custom_id="btn_loop")
    async def loop(self, interaction: discord.Interaction, _):
        async with self.gm.lock:
            self.gm.looping = not self.gm.looping
            state = self.gm.looping
        await interaction.response.send_message(f"Loop is now **{'ON' if state else 'OFF'}**", ephemeral=True)

    @button(label="🔀", style=discord.ButtonStyle.secondary, custom_id="btn_shuffle")
    async def shuffle(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        async with self.gm.lock:
            q = list(self.gm.queue)
            random.shuffle(q)
            self.gm.queue = deque(q)
        await interaction.followup.send("🔀 Queue shuffled.", ephemeral=True)

    @button(label="🔉", style=discord.ButtonStyle.secondary, custom_id="btn_voldown")
    async def voldown(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        async with self.gm.lock:
            self.gm.volume = max(0.0, round(self.gm.volume - 0.1, 2))
            vol = self.gm.volume
        vc = await self._get_vc(interaction)
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = vol
        await interaction.followup.send(f"Volume: {int(vol*100)}%", ephemeral=True)

    @button(label="🔊", style=discord.ButtonStyle.secondary, custom_id="btn_volup")
    async def volup(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        async with self.gm.lock:
            self.gm.volume = min(2.0, round(self.gm.volume + 0.1, 2))
            vol = self.gm.volume
        vc = await self._get_vc(interaction)
        if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = vol
        await interaction.followup.send(f"Volume: {int(vol*100)}%", ephemeral=True)

    @button(label="⏹", style=discord.ButtonStyle.danger, custom_id="btn_stop")
    async def stop(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        vc = await self._get_vc(interaction)
        if vc:
            async with self.gm.lock:
                self.gm.queue.clear()
                self.gm.current = None
            vc.stop()
            try:
                await vc.disconnect()
            except Exception:
                logger.exception("Error disconnecting on stop")
            await interaction.followup.send("⏹ Stopped and cleared queue.", ephemeral=True)
        else:
            await interaction.followup.send("Bot is not connected.", ephemeral=True)

# --- Search panel for command-based selection ---
class _SearchButton(discord.ui.Button):
    def __init__(self, idx: int, title: str, tracks: List[Track], ctx: commands.Context, gm: GuildMusic):
        super().__init__(label=f"{idx+1}", style=discord.ButtonStyle.primary, custom_id=f"search_{idx}")
        self.idx = idx
        self.tracks = tracks
        self.ctx = ctx
        self.gm = gm

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("You can't use this search panel.", ephemeral=True)
            return
        track = self.tracks[self.idx]
        async with self.gm.lock:
            self.gm.queue.append(track)
        await interaction.response.send_message(f"➕ Queued: **{track.title}**", ephemeral=True)
        await start_playback(self.ctx, self.gm)

class SearchPanel(View):
    def __init__(self, tracks: List[Track], ctx: commands.Context, gm: GuildMusic):
        super().__init__(timeout=60)
        self.tracks = tracks
        self.ctx = ctx
        self.gm = gm
        for i, t in enumerate(tracks):
            self.add_item(_SearchButton(i, t.title, tracks, ctx, gm))
        self.add_item(discord.ui.Button(label="Done", style=discord.ButtonStyle.secondary, custom_id="search_done"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author

    async def on_timeout(self):
        try:
            await self.ctx.send("❌ Search timed out.")
        except Exception:
            pass

# --- Commands ---
@bot.command(name="join")
async def cmd_join(ctx: commands.Context):
    await ensure_voice(ctx)
    await ctx.message.add_reaction("✅")

@bot.command(name="leave")
async def cmd_leave(ctx: commands.Context):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    await ctx.message.add_reaction("👋")

@bot.command(name="play", aliases=["p"])
async def cmd_play(ctx: commands.Context, *, query: str):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    gm.last_channel_id = ctx.channel.id
    await ensure_voice(ctx)

    async with ctx.typing():
        try:
            before = len(gm.queue)
            tracks = await ytdl_search(query, ctx, gm)
            after = len(gm.queue)
            if not tracks and after == before and gm.current is None:
                await ctx.reply("❌ No tracks found.")
                return

            if len(tracks) == 1:
                t = tracks[0]
                embed = discord.Embed(
                    title="Added to Queue",
                    description=f"**{t.title}**\n\n[Open on YouTube]({t.webpage_url})",
                    color=discord.Color.blue()
                )
                if t.thumbnail:
                    embed.set_thumbnail(url=t.thumbnail)
                await ctx.send(embed=embed)
            elif len(tracks) > 1:
                desc = "\n".join([f"`{i+1}` • [{t.title}]({t.webpage_url})" for i, t in enumerate(tracks)])
                embed = discord.Embed(title="Added to Queue", description=desc, color=discord.Color.blue())
                if tracks and tracks[0].thumbnail:
                    embed.set_thumbnail(url=tracks[0].thumbnail)
                await ctx.send(embed=embed)

            await start_playback(ctx, gm)
        except Exception:
            logger.exception("Error in cmd_play")
            await ctx.reply("❌ Failed to fetch or queue audio.")

@bot.command(name="skip", aliases=["s"])
async def cmd_skip(ctx: commands.Context):
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await ctx.message.add_reaction("⏭")

@bot.command(name="queue", aliases=["q"])
async def cmd_queue(ctx: commands.Context):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    embeds: List[discord.Embed] = []
    if gm.current:
        embed = discord.Embed(
            title=f"▶️ Now Playing: {gm.current.title}",
            description=f"[Open on YouTube]({gm.current.webpage_url})",
            color=discord.Color.orange()
        )
        if gm.current.thumbnail:
            embed.set_thumbnail(url=gm.current.thumbnail)
        embeds.append(embed)
    async with gm.lock:
        queued = list(gm.queue)[:10]
    if not queued and not gm.current:
        await ctx.send("Queue is empty.")
        return
    for i, track in enumerate(queued):
        embed = discord.Embed(
            title=f"{i+1}. {track.title}",
            description=f"[Open on YouTube]({track.webpage_url})",
            color=discord.Color.blue()
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embeds.append(embed)
    # Send all embeds (Discord may group them or you can send individually depending on embed count)
    for emb in embeds:
        await ctx.send(embed=emb)

@bot.command(name="loop")
async def cmd_loop(ctx: commands.Context):
    gm = STATE.setdefault(ctx.guild.id, GuildMusic(guild_id=ctx.guild.id))
    async with gm.lock:
        gm.looping = not gm.looping
        state = gm.looping
    await ctx.send(f"🔁 Loop is now **{'ON' if state else 'OFF'}**")

@bot.command(name="volume", aliases=["vol"])
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
    async with ctx.typing():
        tracks = await ytdl_search(f"ytsearch10:{query}", ctx, None)
    if not tracks:
        await ctx.send("❌ No results found or network error.")
        return
    desc = "\n".join([f"`{i+1}` • [{t.title}]({t.webpage_url})" for i, t in enumerate(tracks)])
    embed = discord.Embed(title="Search Results", description=desc)
    view = SearchPanel(tracks, ctx, gm)
    await ctx.send(embed=embed, view=view)

@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    embed = discord.Embed(
        title="🎵 BLIND MUSIC Bot Help",
        description="Welcome to **BLIND MUSIC**! Here’s a list of my commands:",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/727/727245.png")
    embed.add_field(name="🎧 Voice", value="`!join` → Join your voice channel\n`!leave` → Leave the channel", inline=False)
    embed.add_field(name="🎶 Music", value="`!play <query>` or `!p <query>` → Play a song\n`!skip` or `!s` → Skip current song\n`!loop` → Toggle loop mode", inline=False)
    embed.add_field(name="📜 Queue", value="`!queue` or `!q` → Show current queue\n`!search <query>` → Search and select a song", inline=False)
    embed.add_field(name="⚙️ Settings", value="`!volume <0-200>` or `!vol <0-200>` → Set volume", inline=False)
    embed.set_footer(text="Tip: Use commands in a text channel while in a voice channel 🎶")
    await ctx.send(embed=embed)

# --- Events & Startup ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

# Keep-alive (optional simple web server) — run in background thread so bot.run() isn't blocked
def keep_alive():
    try:
        from flask import Flask
        app = Flask(__name__)

        @app.route('/')
        def home():
            return "Bot is running"

        app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8080')))
    except Exception:
        logger.exception("Failed to start keep-alive web server")

# Run the bot
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in environment")

threading.Thread(target=keep_alive, daemon=True).start()
bot.run(TOKEN)
