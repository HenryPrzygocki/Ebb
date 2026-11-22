"""Fork: track lists show a track's best quality on TIDAL before it plays."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui.track_table import track_quality_tier  # noqa: E402


@pytest.mark.parametrize("quality,tags,tier", [
    ("HI_RES_LOSSLESS", ["LOSSLESS", "HIRES_LOSSLESS"], "hires"),
    ("LOSSLESS", ["LOSSLESS", "HIRES_LOSSLESS"], "hires"),  # the tags know better than the field
    ("LOSSLESS", ["LOSSLESS"], None),  # CD-quality FLAC: the baseline, no badge
    ("HI_RES", ["LOSSLESS", "MQA"], None),  # former MQA, now served as 16-bit FLAC
    ("HIGH", [], "lossy"),
    ("LOW", None, "lossy"),
    ("HIGH", ["LOSSLESS"], None),
    (None, None, None),  # no quality data (uploads): say nothing
])
def test_quality_tier_comes_from_tidal_metadata(quality, tags, tier):
    assert track_quality_tier(SimpleNamespace(audio_quality=quality, media_metadata_tags=tags)) == tier
