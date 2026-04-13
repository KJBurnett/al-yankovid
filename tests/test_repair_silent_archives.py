import importlib
import json
from pathlib import Path


def _make_archive_entry(root, user_id, timestamp, video_name, metadata_url=None):
    folder = root / user_id / timestamp
    folder.mkdir(parents=True, exist_ok=True)
    video_path = folder / video_name
    video_path.write_bytes(b"video")
    if metadata_url:
        (folder / "metadata.json").write_text(
            json.dumps({"original_url": metadata_url}),
            encoding="utf-8",
        )
    return folder, video_path


def test_resolve_original_url_prefers_metadata(tmp_env, tmp_path):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    folder, video_path = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-00-00",
        "video_normalized.mp4",
        metadata_url="https://example.com/from-metadata",
    )

    file_index = {str(video_path.relative_to(archive_root)): "https://example.com/from-index"}
    folder_index = {str(folder.relative_to(archive_root)): "https://example.com/from-folder-index"}

    url, source = tool.resolve_original_url(folder, video_path, file_index, folder_index)
    assert url == "https://example.com/from-metadata"
    assert source == "metadata"


def test_resolve_original_url_falls_back_to_index(tmp_env, tmp_path):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    folder, video_path = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-00-00",
        "video_normalized.mp4",
    )

    file_index = {str(video_path.relative_to(archive_root)): "https://example.com/from-index"}
    folder_index = {}

    url, source = tool.resolve_original_url(folder, video_path, file_index, folder_index)
    assert url == "https://example.com/from-index"
    assert source == "index:file"


def test_load_index_lookup_normalizes_mixed_paths(tmp_env, tmp_path):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    archive_root.mkdir(exist_ok=True)
    index = {
        "https://example.com/a": r"C:\Users\kyler\Workspace\al-yankovid\archive\user-1\ts-1\clip.mp4",
        "https://example.com/b": "/app/archive/user-2/ts-2/clip.mp4",
    }
    (archive_root / "index.json").write_text(json.dumps(index), encoding="utf-8")

    by_file, by_folder = tool.load_index_lookup(archive_root)

    assert by_file["user-1/ts-1/clip.mp4"] == "https://example.com/a"
    assert by_folder["user-2/ts-2"] == "https://example.com/b"


def test_scan_archive_dry_run_reports_candidate_without_downloading(tmp_env, tmp_path, monkeypatch, capsys):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    folder, video_path = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-00-00",
        "video_normalized.mp4",
        metadata_url="https://example.com/video",
    )

    monkeypatch.setattr(tool, "has_audio_stream", lambda path: False if str(path) == str(video_path) else True)

    called = {"downloaded": False}

    def fake_fresh_download(url):
        called["downloaded"] = True
        return Path("/tmp/repaired.mp4"), True, Path("/tmp/fake-temp")

    monkeypatch.setattr(tool, "fresh_download_with_audio", fake_fresh_download)

    cache_path = tmp_path / "cache.json"
    results = tool.scan_archive(archive_root, apply_changes=False, cache_path=cache_path)
    out = capsys.readouterr().out

    assert results[0]["status"] == "candidate"
    assert "Mode: dry-run" in out
    assert called["downloaded"] is False
    assert video_path.read_bytes() == b"video"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert len(payload["remaining"]) == 1


def test_scan_archive_apply_replaces_file(tmp_env, tmp_path, monkeypatch):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    _, video_path = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-00-00",
        "video_normalized.mp4",
        metadata_url="https://example.com/video",
    )
    repaired = tmp_path / "repaired.mp4"
    repaired.write_bytes(b"repaired-audio")

    monkeypatch.setattr(tool, "has_audio_stream", lambda path: False if str(path) == str(video_path) else True)

    def fake_fresh_download(url):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(exist_ok=True)
        return repaired, True, temp_dir

    monkeypatch.setattr(tool, "fresh_download_with_audio", fake_fresh_download)
    monkeypatch.setattr(tool, "ensure_apply_dependencies", lambda: None)

    cache_path = tmp_path / "cache.json"
    tool.save_cache(
        cache_path,
        tool.build_cache_payload(
            archive_root,
            [
                {
                    "folder": str(video_path.parent),
                    "video": str(video_path),
                    "url": "https://example.com/video",
                    "url_source": "metadata",
                    "status": "candidate",
                    "detail": "cached",
                }
            ],
        ),
    )

    results = tool.scan_archive(archive_root, apply_changes=True, cache_path=cache_path)

    assert results[0]["status"] == "repaired"
    assert video_path.read_bytes() == b"repaired-audio"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["remaining"] == []


def test_scan_archive_missing_url_is_reported(tmp_env, tmp_path, monkeypatch):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    _, video_path = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-00-00",
        "video_normalized.mp4",
    )

    monkeypatch.setattr(tool, "has_audio_stream", lambda path: False if str(path) == str(video_path) else True)

    results = tool.scan_archive(archive_root, apply_changes=False)
    assert results[0]["status"] == "missing_url"


def test_scan_archive_apply_continues_after_repair_failure(tmp_env, tmp_path, monkeypatch):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    _, video_a = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-00-00",
        "a_normalized.mp4",
        metadata_url="https://example.com/a",
    )
    _, video_b = _make_archive_entry(
        archive_root,
        "user-1",
        "2026-03-01-10-05-00",
        "b_normalized.mp4",
        metadata_url="https://example.com/b",
    )

    monkeypatch.setattr(tool, "has_audio_stream", lambda path: False if str(path) in {str(video_a), str(video_b)} else True)
    monkeypatch.setattr(tool, "ensure_apply_dependencies", lambda: None)

    def fake_repair(folder, video_path, url, apply_changes):
        if url.endswith("/a"):
            raise RuntimeError("download blew up")
        return "repaired", "ok"

    monkeypatch.setattr(tool, "repair_entry", fake_repair)

    cache_path = tmp_path / "cache.json"
    tool.save_cache(
        cache_path,
        tool.build_cache_payload(
            archive_root,
            [
                {
                    "folder": str(video_a.parent),
                    "video": str(video_a),
                    "url": "https://example.com/a",
                    "url_source": "metadata",
                    "status": "candidate",
                    "detail": "cached",
                },
                {
                    "folder": str(video_b.parent),
                    "video": str(video_b),
                    "url": "https://example.com/b",
                    "url_source": "metadata",
                    "status": "candidate",
                    "detail": "cached",
                },
            ],
        ),
    )

    results = tool.scan_archive(archive_root, apply_changes=True, cache_path=cache_path)
    statuses = [item["status"] for item in results]
    assert "repair_failed" in statuses
    assert "repaired" in statuses
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert len(payload["remaining"]) == 1


def test_replace_archived_video_falls_back_to_inplace_copy_on_permission_error(tmp_env, tmp_path, monkeypatch):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    target = tmp_path / "target.mp4"
    repaired = tmp_path / "repaired.mp4"
    target.write_bytes(b"old")
    repaired.write_bytes(b"new")

    def fake_copy2(src, dst, *args, **kwargs):
        raise PermissionError("no sibling temp writes on smb")

    monkeypatch.setattr(tool.shutil, "copy2", fake_copy2)

    mode = tool.replace_archived_video(target, repaired)
    assert mode == "inplace"
    assert target.read_bytes() == b"new"


def test_load_or_refresh_candidates_uses_existing_cache(tmp_env, tmp_path, monkeypatch):
    tool = importlib.import_module("tools.repair_silent_archives")
    importlib.reload(tool)

    archive_root = tmp_path / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    cache_path = tmp_path / "cache.json"
    cached = [{"folder": "a", "video": "b", "url": "u", "status": "candidate"}]
    tool.save_cache(cache_path, tool.build_cache_payload(archive_root, cached))

    monkeypatch.setattr(tool, "scan_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("should not rescan")))

    results = tool.load_or_refresh_candidates(archive_root, cache_path)
    assert results == cached
