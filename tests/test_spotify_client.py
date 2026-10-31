import unittest
from services.spotify_client import SpotifyClient, SpotifyTrack


class TestSpotifyClient(unittest.TestCase):
    """Test suite for URL parsing and metadata formatting in SpotifyClient."""

    def test_parse_url_track(self):
        url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
        res = SpotifyClient.parse_url(url)
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "track")
        self.assertEqual(res[1], "4cOdK2wGLETKBW3PvgPWqT")

    def test_parse_url_intl_track(self):
        url = "https://open.spotify.com/intl-fr/track/4cOdK2wGLETKBW3PvgPWqT?si=abc123xyz"
        res = SpotifyClient.parse_url(url)
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "track")
        self.assertEqual(res[1], "4cOdK2wGLETKBW3PvgPWqT")

    def test_parse_url_playlist(self):
        url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
        res = SpotifyClient.parse_url(url)
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "playlist")
        self.assertEqual(res[1], "37i9dQZF1DXcBWIGoYBM5M")

    def test_parse_url_album(self):
        url = "https://open.spotify.com/album/4m2880jivSbbyEGAKfITCa"
        res = SpotifyClient.parse_url(url)
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "album")
        self.assertEqual(res[1], "4m2880jivSbbyEGAKfITCa")

    def test_parse_spotify_uri(self):
        uri = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
        res = SpotifyClient.parse_url(uri)
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "track")
        self.assertEqual(res[1], "4cOdK2wGLETKBW3PvgPWqT")

    def test_parse_invalid_url(self):
        res = SpotifyClient.parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertIsNone(res)

    def test_track_duration_and_search_query(self):
        track = SpotifyTrack(
            spotify_id="123",
            title="Blinding Lights",
            artist="The Weeknd",
            artists=["The Weeknd"],
            album="After Hours",
            duration_ms=200040,
            url="https://open.spotify.com/track/123",
            cover_url="https://example.com/cover.jpg",
            isrc="USUM71904778"
        )
        self.assertEqual(track.duration_seconds, 200)
        self.assertEqual(track.formatted_duration, "03:20")
        self.assertEqual(track.search_query, "The Weeknd - Blinding Lights official audio")


if __name__ == "__main__":
    unittest.main()

