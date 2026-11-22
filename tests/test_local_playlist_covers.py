"""Fork: local playlists open again. upstream's move into src/ dropped
PlaylistManager.get_cover_refs, which their page and search cards call."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.playlist import PlaylistManager  # noqa: E402


def test_cover_refs_are_one_per_album_newest_first_and_capped():
    mgr = PlaylistManager.__new__(PlaylistManager)
    entry = lambda album_id, cover, name="": {"album_id": album_id, "album_name": name, "cover": cover}  # noqa: E731
    playlist = {"tracks": [
        entry(1, "a.jpg"), entry(2, "b.jpg"), entry(1, "a2.jpg"), entry(None, "", "No Cover"),
        entry(None, "c.jpg", "Loose"), entry(3, "d.jpg"), entry(4, "e.jpg"), entry(5, "f.jpg"),
    ]}
    assert mgr.get_cover_refs(playlist) == ["f.jpg", "e.jpg", "d.jpg", "c.jpg"]
    assert mgr.get_cover_refs(playlist, limit=10) == ["f.jpg", "e.jpg", "d.jpg", "c.jpg", "a2.jpg", "b.jpg"]
    assert mgr.get_cover_refs({"tracks": []}) == [] and mgr.get_cover_refs(None) == []
