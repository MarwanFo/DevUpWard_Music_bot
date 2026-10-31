# Project Specifications (Cahier des Charges): Python Spotify Music Bot

**Project Title:** Python Music Bot with Spotify Integration  
**Document Version:** 1.0  
**Language:** Python 3.10+  
**Target Platform:** Discord (adaptable to Telegram/Slack)  

---

## 1. Project Overview & Context

### 1.1 Introduction
The goal of this project is to design, develop, and deploy an automated Music Bot built in Python that integrates with the official **Spotify Web API**. The bot will allow users on a communication platform (primarily Discord) to search for music, retrieve metadata, manage playlists, get song recommendations, and play audio seamlessly within voice channels.

### 1.2 Technical Note on Spotify API & Audio Streaming
* **Important Architecture Constraint:** The official Spotify Web API provides rich metadata (track names, artists, albums, playlists, recommendations, audio features) and playback control for Spotify Premium devices, **but it does not provide raw full-length audio streams** due to DRM (Digital Rights Management) restrictions.
* **Solution:** The bot will use the **Spotify Web API** (`spotipy`) as the primary intelligence and metadata engine (resolving links, extracting tracklists, searching) and pair it with an audio extraction library (`yt-dlp` + `FFmpeg` or `Lavalink`) to stream the corresponding audio into the voice channel.

---

## 2. Project Objectives
1. **Seamless Spotify Integration:** Allow users to paste any Spotify URL (Track, Album, Playlist, Artist) or search query to queue music.
2. **High-Quality Audio Playback:** Provide lag-free, stable audio streaming in voice channels with full queue management.
3. **Music Discovery:** Leverage Spotify's recommendation engine to offer "Autoplay / Radio" features based on current tracks.
4. **User-Friendly Interface:** Implement modern interactive controls (Slash commands `/`, interactive buttons, and rich embeds).

---

## 3. Scope of Work & Functional Requirements

### 3.1 Music Playback & Queue Management
* **`/play [query or Spotify URL]`**: 
  * If a Spotify Track URL is provided, fetch track metadata (Title, Artist, ISRC, Cover Art) and stream matching audio.
  * If a Spotify Playlist/Album URL is provided, extract all tracks asynchronously and add them to the server queue.
  * If a text query is provided, search Spotify for the closest track match, display metadata, and play audio.
* **Playback Controls:**
  * `/pause` & `/resume`: Pause and resume current playback.
  * `/skip`: Skip the current track and play the next in the queue.
  * `/stop`: Clear the queue and disconnect the bot from the voice channel.
  * `/volume [0-100]`: Adjust the playback volume.
* **Queue Operations:**
  * `/queue`: Display the current list of upcoming songs with pagination.
  * `/shuffle`: Randomize the current order of tracks in the queue.
  * `/loop [off | track | queue]`: Toggle repeat modes.
  * `/remove [index]`: Remove a specific track from the queue.

### 3.2 Spotify-Specific Features (Metadata & Discovery)
* **`/nowplaying`**: Display a rich card (Embed) containing the Spotify album cover, track name, artist(s), release date, track duration, and a direct link to open the song in Spotify.
* **`/recommend` (or Autoplay Mode)**: Use Spotify's Recommendation API endpoint to automatically queue 5 similar songs based on the seed track/artist when the queue runs out.
* **`/trackinfo [query]`**: Fetch Spotify Audio Features (BPM/Tempo, Key, Danceability, Energy, Acousticness) for music enthusiasts.
* **`/artist [name]`**: Display an artist's top 5 tracks on Spotify, follower count, genres, and profile image.

### 3.3 User & Playlist Management (Optional / Phase 2)
* **Custom Bot Playlists:** Allow users to save the current server queue into a custom database playlist or export it directly to their personal Spotify account (requires OAuth2 Authorization Code Flow).
* **`/lyrics`**: Fetch and display lyrics for the currently playing Spotify track (via Genius or Musixmatch API integration).

---

## 4. Non-Functional Requirements

### 4.1 Performance & Scalability
* **Asynchronous Execution:** All network requests (Spotify API calls, audio resolving, Discord events) must be non-blocking (`asyncio`) so the bot can handle multiple servers simultaneously without audio stuttering.
* **Rate Limit Handling:** Implement caching and proper backoff strategies to respect Spotify Web API rate limits (HTTP 429 responses).
* **Response Time:** Bot commands should acknowledge user input within `< 1.5 seconds`.

### 4.2 Security
* **Credential Management:** API keys (`SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`, `DISCORD_BOT_TOKEN`) must be stored in environment variables (`.env` file) and excluded from version control (`.gitignore`).
* **Permission Checks:** Ensure users are in the same voice channel as the bot before allowing them to skip, stop, or modify the queue.

### 4.3 Reliability & Maintainability
* **Auto-Disconnect:** The bot must automatically leave the voice channel after 5 minutes of inactivity or if left alone in the channel to save server resources.
* **Modular Codebase:** Use Cogs/Extensions to separate playback commands, Spotify API wrappers, and error handlers.

---

## 5. Technical Stack & Architecture

### 5.1 Software & Libraries
| Component | Technology / Library | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.10 or higher | Core programming language |
| **Platform Wrapper** | `discord.py` (v2.3+) or `Pycord` | Interacting with Discord API & Voice |
| **Spotify Client** | `spotipy` (or `asyncspotipy`) | Interfacing with Spotify Web API |
| **Audio Resolver** | `yt-dlp` or `Wavelink` (Lavalink) | Fetching audio streams for playback |
| **Audio Processing** | `FFmpeg` + `PyNaCl` | Encoding/streaming audio packets to voice |
| **Database** | `SQLite` (via `aiosqlite`) or `MongoDB` | Storing server settings, prefixes, and saved queues |
| **Environment** | `python-dotenv` | Managing secret tokens and environment variables |

### 5.2 Authentication Flow
* **Client Credentials Flow (Default):** Used for searching tracks, reading public playlists, fetching albums, and getting recommendations without requiring individual users to log in.
* **Authorization Code Flow (Optional Phase 2):** Required only if the bot needs to read a user's private playlists or create/modify playlists on a user's personal Spotify account.

### 5.3 System Architecture Flow
1. **User Input:** User executes `/play https://open.spotify.com/track/...`
2. **Command Handler:** Bot parses the URL and identifies it as a Spotify resource.
3. **Spotify API Module:** Queries Spotify API using `Client Credentials` to retrieve exact metadata (`Artist - Track Name`, Duration, Thumbnail URL).
4. **Audio Stream Resolver:** Searches audio source for `"Artist - Track Name official audio"`, extracts the stream URL, and passes it to `FFmpeg`.
5. **Voice Client:** Streams the audio buffer to the voice channel while displaying the Spotify metadata and interactive buttons (`Pause`, `Skip`, `Loop`) in the text channel.

---

## 6. Project Structure (Directory Layout)

```text
spotify-music-bot/
├── .env.example             # Template for environment variables
├── .gitignore               # Ignored files (.env, __pycache__, etc.)
├── requirements.txt         # Python dependencies
├── README.md                # Setup and usage documentation
├── main.py                  # Bot entry point and initialization
├── config/
│   └── settings.py          # Configuration loader
├── cogs/
│   ├── music.py             # Playback, queue, and voice commands
│   ├── spotify_info.py      # Discovery, recommendations, and track stats
│   └── admin.py             # Bot status, error handling, server config
├── services/
│   ├── spotify_client.py    # Wrapper around Spotipy for clean API calls
│   └── audio_source.py      # yt-dlp / FFmpeg audio player and queue logic
└── utils/
    ├── embeds.py            # Standardized UI Embed builders
    └── views.py             # Interactive buttons (Pause, Skip, Stop UI)
```

---

## 7. Development Milestones & Phases

* **Phase 1: Environment Setup & API Connections (Week 1)**
  * Create Spotify Developer Application & Discord Bot Application.
  * Set up Python virtual environment, install dependencies (`discord.py`, `spotipy`, `FFmpeg`).
  * Build the `spotify_client.py` service to test fetching tracks, albums, and playlists.
* **Phase 2: Core Audio Engine & Queue System (Week 2)**
  * Implement voice channel connection logic (`join`, `leave`).
  * Build the Queue data structure per server (Guild).
  * Bridge Spotify metadata with the audio stream resolver (`yt-dlp` + `FFmpeg`) to play single tracks and playlists.
* **Phase 3: Advanced Controls & Spotify Discovery (Week 3)**
  * Add `/skip`, `/pause`, `/loop`, `/shuffle`, and `/remove`.
  * Implement interactive UI buttons below the "Now Playing" message.
  * Integrate Spotify Recommendations API for Autoplay/Radio mode.
* **Phase 4: Testing, Optimization & Deployment (Week 4)**
  * Stress-test large playlists (100+ songs) using pagination/lazy loading so the bot doesn't freeze.
  * Implement error handling (private playlists, invalid links, missing permissions).
  * Containerize with `Docker` (including `FFmpeg`) and deploy to a VPS (e.g., DigitalOcean, AWS, or Railway).

---

## 8. Deliverables
1. **Source Code:** Clean, documented Python code hosted on a Git repository (GitHub/GitLab).
2. **Documentation (`README.md`):** Step-by-step guide on how to obtain Spotify/Discord API keys, install `FFmpeg`, and run the bot locally or via Docker.
3. **Deployment Artifacts:** `Dockerfile` and `docker-compose.yml` for one-click deployment.