"""
Integration tests — exercise real yt-dlp + ffmpeg downloads.
Marked with pytest.mark.integration; excluded from default CI runs (see pytest.ini).

Run manually:
    pytest -m integration -v

Fill in the URL placeholders below before running.
"""
import os
import json
import pytest
import importlib

pytestmark = pytest.mark.integration

# TODO: Replace these with real URLs before running integration tests
TIKTOK_URL = "PLACEHOLDER_TIKTOK_URL"
YOUTUBE_URL = "PLACEHOLDER_YOUTUBE_URL"


def test_tiktok_download_has_audio(integration_archive):
    """Verifies the TikTok URL that previously had audio issues downloads with audio."""
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    result = vh.process_video(TIKTOK_URL, user_id='integration_test')
    path, title, description, metadata_path, sub_path, service, has_audio = result

    assert path is not None, "process_video returned no path"
    assert os.path.exists(path), f"Archived file not found at {path}"
    assert has_audio is True, "TikTok video came through without audio"
    assert service == 'TikTok'


def test_youtube_video_download_has_audio(integration_archive):
    """Verifies a regular YouTube video (non-Shorts) downloads correctly with audio."""
    vh = importlib.import_module('video_handler')
    importlib.reload(vh)

    result = vh.process_video(YOUTUBE_URL, user_id='integration_test')
    path, title, description, metadata_path, sub_path, service, has_audio = result

    assert path is not None, "process_video returned no path"
    assert os.path.exists(path), f"Archived file not found at {path}"
    assert has_audio is True, "YouTube video came through without audio"
    assert title, "Expected a non-empty title"
    assert service in ('Youtube', 'YouTube'), f"Unexpected service: {service}"


def test_integration_archive_is_isolated(integration_archive):
    """
    Sanity check: confirms the integration_archive fixture provides a fresh
    empty archive so tests can't produce false positives from prior cached downloads.
    """
    index_path = os.path.join(integration_archive, 'index.json')
    if os.path.exists(index_path):
        with open(index_path) as f:
            idx = json.load(f)
        assert idx == {}, "Integration archive was not clean at test start — possible false-positive risk"
