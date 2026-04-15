import importlib
import os
import shutil
import tempfile

import pytest


def _network_tests_enabled():
    return os.getenv("RUN_NETWORK_TESTS", "").strip().lower() in {"1", "true", "yes"}


@pytest.mark.skipif(not _network_tests_enabled(), reason="Set RUN_NETWORK_TESTS=1 to enable network integration tests")
def test_youtube_shorts_download_has_audio():
    vh = importlib.import_module("video_handler")
    importlib.reload(vh)

    url = os.getenv("YOUTUBE_SHORTS_TEST_URL", "https://www.youtube.com/shorts/MFU1A7jJTYU")
    temp_dir = tempfile.mkdtemp(prefix="integration_shorts_")
    try:
        info = vh.get_video_info(url)
        assert info
        assert info.get("id")

        path = vh.download_video(url, temp_dir, video_id=info.get("id"))
        assert path
        assert os.path.exists(path)
        assert vh.has_audio_stream(path) is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# Instagram reel that was previously reported as downloading muted/silent.
# The URL below is the specific reel used to surface the bug.
INSTAGRAM_REEL_URL = os.getenv(
    "INSTAGRAM_REEL_TEST_URL",
    "https://www.instagram.com/reel/DXEweNQjXRd/?igsh=MWp3aTE0dzVrZmhydQ==",
)


@pytest.mark.skipif(not _network_tests_enabled(), reason="Set RUN_NETWORK_TESTS=1 to enable network integration tests")
def test_instagram_reel_get_video_info_returns_metadata():
    """Verify yt-dlp can extract metadata from the Instagram reel without error."""
    vh = importlib.import_module("video_handler")
    importlib.reload(vh)

    info = vh.get_video_info(INSTAGRAM_REEL_URL)

    assert info, "get_video_info returned empty/None for Instagram reel"
    assert info.get("id"), "Expected a non-empty video ID in metadata"
    assert info.get("extractor_key", "").lower() in (
        "instagram", "instagramstory", "instagramigtv",
    ), f"Unexpected extractor_key: {info.get('extractor_key')}"


# TikTok video that was reported as failing with "Requested format is not available".
# Short URL redirects to the full TikTok video page.
TIKTOK_VIDEO_URL = os.getenv(
    "TIKTOK_TEST_URL",
    "https://www.tiktok.com/t/ZP8gUYuFD/",
)


@pytest.mark.skipif(not _network_tests_enabled(), reason="Set RUN_NETWORK_TESTS=1 to enable network integration tests")
def test_tiktok_get_video_info_returns_metadata():
    """Verify yt-dlp can extract metadata from a TikTok video without error."""
    vh = importlib.import_module("video_handler")
    importlib.reload(vh)

    info = vh.get_video_info(TIKTOK_VIDEO_URL)

    assert info, "get_video_info returned empty/None for TikTok video"
    assert info.get("id"), "Expected a non-empty video ID in metadata"
    assert info.get("extractor_key", "").lower() in (
        "tiktok",
    ), f"Unexpected extractor_key: {info.get('extractor_key')}"


@pytest.mark.skipif(not _network_tests_enabled(), reason="Set RUN_NETWORK_TESTS=1 to enable network integration tests")
def test_tiktok_download_has_audio():
    """Regression test: TikTok video must download successfully with an audio stream.

    TikTok serves combined (muxed) streams rather than separate video+audio tracks,
    so format selectors that require merging (e.g. bestvideo+bestaudio) fail with
    "Requested format is not available". This test verifies that the format-selector
    fallback chain reaches 'best' and produces a playable file with audio.
    """
    vh = importlib.import_module("video_handler")
    importlib.reload(vh)

    temp_dir = tempfile.mkdtemp(prefix="integration_tiktok_")
    try:
        info = vh.get_video_info(TIKTOK_VIDEO_URL)
        assert info and info.get("id"), "Could not fetch TikTok video metadata"

        path = vh.download_video(TIKTOK_VIDEO_URL, temp_dir, video_id=info.get("id"))

        assert path is not None, "download_video returned None — no file was produced"
        assert os.path.exists(path), f"Expected downloaded file at {path!r} but it does not exist"
        assert path.endswith(".mp4"), f"Expected an MP4 file, got: {path!r}"
        assert vh.has_audio_stream(path) is True, (
            f"Downloaded TikTok video has no audio stream — the video would be muted when sent. "
            f"File: {path!r}"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.skipif(not _network_tests_enabled(), reason="Set RUN_NETWORK_TESTS=1 to enable network integration tests")
def test_instagram_reel_download_has_audio():
    """Regression test: Instagram reel must download with an audio stream (not muted).

    This test was added after a report that the bot was uploading silent/muted
    videos for Instagram reels. It exercises the full yt-dlp download + format
    fallback chain and asserts that the resulting file has an audio stream.
    """
    vh = importlib.import_module("video_handler")
    importlib.reload(vh)

    temp_dir = tempfile.mkdtemp(prefix="integration_ig_reel_")
    try:
        info = vh.get_video_info(INSTAGRAM_REEL_URL)
        assert info and info.get("id"), "Could not fetch Instagram reel metadata"

        path = vh.download_video(INSTAGRAM_REEL_URL, temp_dir, video_id=info.get("id"))

        assert path is not None, "download_video returned None — no file was produced"
        assert os.path.exists(path), f"Expected downloaded file at {path!r} but it does not exist"
        assert path.endswith(".mp4"), f"Expected an MP4 file, got: {path!r}"
        assert vh.has_audio_stream(path) is True, (
            f"Downloaded Instagram reel has no audio stream — the video would be muted when sent. "
            f"File: {path!r}"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
