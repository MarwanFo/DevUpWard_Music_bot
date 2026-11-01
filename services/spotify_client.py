import asyncio
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

import spotipy
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.exceptions import SpotifyException

from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger("SpotifyClient")

# Regex to match and parse Spotify URLs & URIs
SPOTIFY_URL_REGEX = re.compile(
    r"(?:https?:\/\/open\.spotify\.com\/(?:intl-[a-z]{2}\/)?|spotify:)(track|album|playlist|artist)[\/:]([a-zA-Z0-9]+)"
)


@dataclass
class SpotifyTrack:
    """Represents a standardized, resolved Spotify track."""
    spotify_id: str
    title: str
    artist: str
    artists: List[str]
    album: str
    duration_ms: int
    url: str
    cover_url: Optional[str] = None
    isrc: Optional[str] = None

    @property
    def duration_seconds(self) -> int:
        return self.duration_ms // 1000

    @property
    def formatted_duration(self) -> str:
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def search_query(self) -> str:
        """Query optimized for YouTube / YouTube Music audio resolution."""
        return f"{self.artist} - {self.title} official audio"


@dataclass
class SpotifyCollection:
    """Represents a collection of tracks (Playlist or Album)."""
    collection_type: str  # 'playlist' or 'album'
    spotify_id: str
    title: str
    owner_or_artist: str
    total_tracks: int
    cover_url: Optional[str]
    url: str
    tracks: List[SpotifyTrack] = field(default_factory=list)


class SpotifyClient:
    """
    Asynchronous wrapper around the official Spotify Web API.
    All Spotipy calls are dispatched to a thread pool executor to prevent
    blocking the asyncio event loop.
    """

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id or settings.SPOTIPY_CLIENT_ID
        self.client_secret = client_secret or settings.SPOTIPY_CLIENT_SECRET
        self._sp: Optional[spotipy.Spotify] = None
        self._auth_manager: Optional[SpotifyClientCredentials] = None
        self._initialize_client()

    def _initialize_client(self):
        """Initializes the Spotipy client with credentials if provided."""
        if self.client_id and self.client_secret:
            try:
                self._auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    cache_handler=MemoryCacheHandler()
                )
                self._sp = spotipy.Spotify(
                    auth_manager=self._auth_manager,
                    requests_timeout=10,
                    retries=3
                )
                logger.info("Spotify API client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Spotify client: {e}")
                self._sp = None
        else:
            logger.warning("Spotify credentials missing. Spotify client is in unauthenticated mode.")

    @property
    def is_authenticated(self) -> bool:
        return self._sp is not None

    @staticmethod
    def parse_url(url_or_query: str) -> Optional[Tuple[str, str]]:
        """
        Extracts resource type ('track', 'album', 'playlist', 'artist') and ID from a Spotify URL/URI.
        Returns: (type, id) or None if not a Spotify URL.
        """
        match = SPOTIFY_URL_REGEX.search(url_or_query.strip())
        if match:
            return match.group(1), match.group(2)
        return None

    def _parse_track_payload(self, data: Dict[str, Any]) -> SpotifyTrack:
        """Parses a Spotify API track dict into a typed SpotifyTrack instance."""
        artists = [a.get("name", "Unknown Artist") for a in data.get("artists", [])]
        main_artist = artists[0] if artists else "Unknown Artist"

        # Album & Cover Art extraction
        album_data = data.get("album", {})
        album_name = album_data.get("name", "Unknown Album")
        images = album_data.get("images", [])
        cover_url = images[0].get("url") if images else None

        # External IDs (ISRC)
        external_ids = data.get("external_ids", {})
        isrc = external_ids.get("isrc")

        spotify_id = data.get("id") or ""
        external_urls = data.get("external_urls", {})
        spotify_url = external_urls.get("spotify", f"https://open.spotify.com/track/{spotify_id}")

        return SpotifyTrack(
            spotify_id=spotify_id,
            title=data.get("name", "Unknown Title"),
            artist=main_artist,
            artists=artists,
            album=album_name,
            duration_ms=data.get("duration_ms", 0),
            url=spotify_url,
            cover_url=cover_url,
            isrc=isrc
        )

    async def get_track(self, track_id: str) -> Optional[SpotifyTrack]:
        """Fetches metadata for a single track by Spotify ID or URL."""
        if not self._sp:
            raise RuntimeError("Spotify client is not initialized or credentials are missing.")

        parsed = self.parse_url(track_id)
        clean_id = parsed[1] if parsed else track_id

        try:
            data = await asyncio.to_thread(self._sp.track, clean_id)
            return self._parse_track_payload(data)
        except SpotifyException as e:
            logger.error(f"Spotify error fetching track '{clean_id}': {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error fetching track '{clean_id}': {e}")
            return None

    async def get_album(self, album_id: str) -> Optional[SpotifyCollection]:
        """Fetches all tracks from an album by Spotify ID or URL."""
        if not self._sp:
            raise RuntimeError("Spotify client is not initialized.")

        parsed = self.parse_url(album_id)
        clean_id = parsed[1] if parsed else album_id

        try:
            album_info = await asyncio.to_thread(self._sp.album, clean_id)
            album_name = album_info.get("name", "Unknown Album")
            artists = [a.get("name") for a in album_info.get("artists", [])]
            cover_url = album_info.get("images", [{}])[0].get("url") if album_info.get("images") else None
            album_url = album_info.get("external_urls", {}).get("spotify", "")

            # Paginate through all album tracks
            tracks: List[SpotifyTrack] = []
            results = album_info.get("tracks", {})

            while results:
                for item in results.get("items", []):
                    # Album track objects omit full album payload, inject album metadata
                    item["album"] = {"name": album_name, "images": album_info.get("images", [])}
                    tracks.append(self._parse_track_payload(item))

                if results.get("next"):
                    results = await asyncio.to_thread(self._sp.next, results)
                else:
                    break

            return SpotifyCollection(
                collection_type="album",
                spotify_id=clean_id,
                title=album_name,
                owner_or_artist=", ".join(artists),
                total_tracks=len(tracks),
                cover_url=cover_url,
                url=album_url,
                tracks=tracks
            )
        except Exception as e:
            logger.exception(f"Failed to fetch Spotify album '{clean_id}': {e}")
            return None

    async def get_playlist(self, playlist_id: str) -> Optional[SpotifyCollection]:
        """Fetches all tracks from a public or unlisted Spotify playlist."""
        if not self._sp:
            raise RuntimeError("Spotify client is not initialized.")

        parsed = self.parse_url(playlist_id)
        clean_id = parsed[1] if parsed else playlist_id

        try:
            playlist_info = await asyncio.to_thread(
                self._sp.playlist,
                clean_id,
                fields="id,name,owner.display_name,images,external_urls,tracks.total,tracks.items,tracks.next"
            )
            title = playlist_info.get("name", "Unknown Playlist")
            owner = playlist_info.get("owner", {}).get("display_name", "Unknown Curator")
            cover_url = playlist_info.get("images", [{}])[0].get("url") if playlist_info.get("images") else None
            playlist_url = playlist_info.get("external_urls", {}).get("spotify", "")

            tracks: List[SpotifyTrack] = []
            results = playlist_info.get("tracks", {})

            while results:
                for item in results.get("items", []):
                    track_data = item.get("track")
                    # Ignore episodes/podcasts or unavailable local files
                    if track_data and track_data.get("id"):
                        tracks.append(self._parse_track_payload(track_data))

                if results.get("next"):
                    results = await asyncio.to_thread(self._sp.next, results)
                else:
                    break

            return SpotifyCollection(
                collection_type="playlist",
                spotify_id=clean_id,
                title=title,
                owner_or_artist=owner,
                total_tracks=len(tracks),
                cover_url=cover_url,
                url=playlist_url,
                tracks=tracks
            )
        except Exception as e:
            logger.exception(f"Failed to fetch Spotify playlist '{clean_id}': {e}")
            return None

    async def search(self, query: str, limit: int = 1) -> List[SpotifyTrack]:
        """Searches Spotify for tracks matching the given text query."""
        if not self._sp:
            raise RuntimeError("Spotify client is not initialized.")

        try:
            results = await asyncio.to_thread(
                self._sp.search,
                q=query,
                limit=limit,
                type="track"
            )
            items = results.get("tracks", {}).get("items", [])
            return [self._parse_track_payload(item) for item in items]
        except Exception as e:
            logger.exception(f"Error searching Spotify for '{query}': {e}")
            return []


# Global singleton instance
spotify_client = SpotifyClient()

