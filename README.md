# Musify Discord Music Bot

A Discord music bot with interactive buttons, queue, search, and YouTube playback.  
Supports Discord.py v2+, yt-dlp, FFmpeg, and runs on any OS.

## Features

- Play music from YouTube with `!play <song name or URL>`
- Search YouTube and pick from top 10 results with `!search <keywords>`
- Interactive control panel (pause, skip, loop, shuffle, volume, stop)
- Queue management
- Album art/thumbnails in embeds
- Loop and shuffle support
- Volume control

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd Musify\ bot
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install FFmpeg

- **Windows:** [Download FFmpeg](https://ffmpeg.org/download.html), extract, and add to your PATH.
- **Linux:**  
  ```bash
  sudo apt install ffmpeg
  ```
- **macOS:**  
  ```bash
  brew install ffmpeg
  ```

### 4. Set up your Discord bot token

- Create a `.env` file in the project folder:
  ```
  DISCORD_TOKEN=your_bot_token_here
  ```
- Get your bot token from the [Discord Developer Portal](https://discord.com/developers/applications).

## Running the Bot

```bash
python musify.py
```

If hosting on Replit/Heroku, make sure to install `flask` and keep the `.env` file with your token.

## Quick Start

1. **Install Python 3.10+**  
   Make sure you have Python installed. You can check with:
   ```bash
   python --version
   ```

2. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd "Musify bot"
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg**  
   - **Windows:** [Download FFmpeg](https://ffmpeg.org/download.html), extract, and add to PATH.
   - **Linux:** `sudo apt install ffmpeg`
   - **macOS:** `brew install ffmpeg`

5. **Create your `.env` file**  
   In the project folder, create a file named `.env` and add your Discord bot token:
   ```
   DISCORD_TOKEN=your_bot_token_here
   ```

6. **Run the bot**
   ```bash
   python musify.py
   ```

7. **Invite your bot to your Discord server**  
   Use the OAuth2 URL from the Discord Developer Portal.

## Usage

Invite your bot to your server.  
Type commands in any text channel where the bot has access.

### Main Commands

- `!play <song name or YouTube URL>`  
  Adds a song to the queue and starts playback.

- `!search <keywords>`  
  Shows top 10 YouTube results with album art. Click a button to add to queue.

- `!skip` or `!s`  
  Skip the current song.

- `!queue` or `!q`  
  Show the next 15 songs in the queue.

- `!loop`  
  Toggle loop mode.

- `!volume <0-200>` or `!vol <0-200>`  
  Set playback volume (default 50%).

- `!join`  
  Make the bot join your voice channel.

- `!leave`  
  Disconnect the bot from voice.

### Control Panel Buttons

- ⏮ Previous
- ⏯ Pause/Resume
- ⏭ Skip
- 🔁 Loop
- 🔀 Shuffle
- 🔉 Volume Down
- 🔊 Volume Up
- ⏹ Stop

## Troubleshooting

- **Bot not joining voice:**  
  Make sure you are in a voice channel and the bot has permission to join/speak.

- **No sound / playback issues:**  
  Ensure FFmpeg is installed and in your system PATH.

- **Slow playback or timeouts:**  
  Check your internet connection. yt-dlp and FFmpeg require access to YouTube.

- **Bot token errors:**  
  Make sure `.env` contains `DISCORD_TOKEN=your_token_here`.

## Hosting

- Works on VPS, local machine, Replit, Heroku, etc.
- For Replit/Heroku, a keepalive web server is included in the code.

## License

MIT

## Credits

- [discord.py](https://github.com/Rapptz/discord.py)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/)
