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
