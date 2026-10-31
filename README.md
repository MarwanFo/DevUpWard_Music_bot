# 🎵 Spotify Music Bot (Discord)

A production-grade, asynchronous Discord Music Bot built with **Python 3.10+**, **discord.py (v2)**, and the official **Spotify Web API**. It features Just-In-Time (JIT) audio resolution, SQLite caching, Discord UI V2 interactive buttons, and auto-disconnect management.

---

## ⚡ Core Features

* **Spotify Metadata Integration:** Queue single tracks, full albums, and playlists (with pagination) directly from Spotify URLs.
* **Just-In-Time (JIT) Audio Streaming:** Audio is resolved via `yt-dlp` + `FFmpeg` immediately prior to playback, eliminating blocking and minimizing rate limits.
* **Stream URL Caching:** Resolved audio streams are cached in an asynchronous SQLite database (`aiosqlite`) with TTL, speeding up repeat track playback to `< 10ms`.
* **Interactive Player UI (Discord V2 Components):**
  * Live Now Playing card with Spotify cover art and duration.
  * Direct clickable buttons: `⏯ Pause/Resume`, `⏭ Skip`, `⏹ Stop`, `🔁 Loop Mode`, and `🔀 Shuffle`.
* **Paginated Queue:** Browse long queues with `◀ Previous` / `Next ▶` buttons.
* **Discovery & Lyrics:**
  * `/artist`: View artist profile, follower stats, genres, and Top 5 popular tracks.
  * `/trackinfo`: Spotify audio features (BPM, danceability, energy).
  * `/lyrics`: Instant lyrics fetched from Lrclib with pagination.
* **Resource Friendly & Resilient:** Automatic disconnection after 5 minutes of inactivity or when left alone in a voice channel.

---

## 📁 Project Architecture

```text
musicbot/
├── .env.example             # Configuration template
├── requirements.txt         # Pinned production dependencies
├── main.py                  # Bot entry point & extension loader
├── config/
│   └── settings.py          # Pydantic-based settings validation
├── cogs/
│   ├── admin.py             # Diagnostics, /ping, and latency metrics
│   ├── music.py             # Playback, queue, and voice commands
│   └── spotify_info.py      # /artist, /trackinfo, and /lyrics
├── services/
│   ├── spotify_client.py    # Async Spotify Web API wrapper
│   ├── audio_source.py      # yt-dlp & FFmpeg audio pipeline
│   ├── player.py            # Per-guild playback state machine
│   └── database.py          # SQLite stream caching & settings
├── utils/
│   ├── logger.py            # Colorized & rotating file logging
│   └── views.py             # Discord UI interactive views
├── tests/
│   └── test_spotify_client.py # Unit tests
├── Dockerfile               # Container build file
└── docker-compose.yml       # Production container orchestration
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites

* **Python 3.10+** (Tested with Python 3.12 & 3.13)
* **FFmpeg** installed and accessible in your system `PATH` (or specified via `FFMPEG_PATH`).
* A **Discord Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications).
* A **Spotify Client ID & Secret** from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

### 2. Installation

1. Clone or navigate to the repository:
   ```bash
   cd musicbot
   ```

2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .\.venv\Scripts\activate

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure your `.env` file:
   ```bash
   cp .env.example .env
   ```
   Fill in your credentials:
   ```env
   DISCORD_BOT_TOKEN=your_token_here
   SPOTIPY_CLIENT_ID=your_spotify_client_id
   SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
   # Optional: Set your test server ID for instant command synchronization
   DEV_GUILD_ID=
   ```

### 3. Running the Bot

```bash
python main.py
```

---

## 🐳 Docker Deployment

To run in the background 24/7 with auto-restart:

```bash
docker compose up -d --build
```

To view logs:
```bash
docker compose logs -f
```

---

## 🎮 Command Reference

| Command | Description |
| :--- | :--- |
| `/play [url or keywords]` | Queues a Spotify track, album, playlist, or searches keywords. |
| `/pause` | Pauses current playback. |
| `/resume` | Resumes paused playback. |
| `/skip` | Skips to the next track. |
| `/stop` | Stops playback, clears the queue, and disconnects. |
| `/queue [page]` | Displays upcoming songs with interactive pagination buttons. |
| `/nowplaying` | Shows the currently playing song with interactive playback buttons. |
| `/volume [0-100]` | Adjusts playback volume. |
| `/loop [off\|track\|queue]` | Toggles repeat modes. |
| `/shuffle` | Randomizes the current queue order. |
| `/remove [index]` | Removes a specific song by its queue position number. |
| `/artist [name]` | Shows artist profile, followers, and Top 5 songs. |
| `/trackinfo [query]` | Displays detailed Spotify audio characteristics (BPM, Energy, etc.). |
| `/lyrics [query]` | Fetches song lyrics (defaults to current playing track). |
| `/ping` | Displays WebSocket and API round-trip latency. |
| `/status` | Shows server count, voice connections, and uptime. |

---

## 🛡️ Anti-Bot & Throttling Notes

If your bot runs in a cloud environment (AWS, DigitalOcean, Hetzner), YouTube may occasionally challenge connections. You can place an exported `cookies.txt` file in the root directory; `audio_source.py` will detect and load it automatically to authenticate extraction.

