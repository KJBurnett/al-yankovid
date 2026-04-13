import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
    
video_handler = None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan archive folders for silent videos and optionally repair them in place."
    )
    parser.add_argument("--archive-root", required=True, help="Path to the archive root.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Replace silent archived videos in place after a successful repair.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after processing this many archive folders.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-folder details for skipped and successful items.",
    )
    parser.add_argument(
        "--include-ok",
        action="store_true",
        help="Print non-silent files in dry-run or verbose output.",
    )
    parser.add_argument(
        "--cache-path",
        default=str(REPO_ROOT / "tools" / ".repair_silent_archives_cache.json"),
        help="Path to the repair cache JSON file.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Rescan the archive and overwrite the cached candidate list.",
    )
    return parser.parse_args()


def log(message):
    print(message, flush=True)


def get_video_handler():
    global video_handler
    if video_handler is None:
        import video_handler as vh
        video_handler = vh
    return video_handler


def ensure_apply_dependencies():
    vh = get_video_handler()
    vh.check_dependencies()
    return vh


def extract_archive_relative_path(raw_path):
    normalized = raw_path.replace("\\", "/")
    marker = "/archive/"
    if marker in normalized:
        return normalized.split(marker, 1)[1].lstrip("/")
    return None


def normalize_rel_key(path_value):
    return str(path_value).replace("\\", "/").lstrip("/")


def load_index_lookup(archive_root):
    index_path = Path(archive_root) / "index.json"
    if not index_path.exists():
        return {}, {}

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    by_file = {}
    by_folder = {}
    for url, raw_path in index.items():
        rel_path = extract_archive_relative_path(raw_path)
        if not rel_path:
            continue
        rel_path = Path(rel_path)
        by_file[normalize_rel_key(rel_path)] = url
        by_folder[normalize_rel_key(rel_path.parent)] = url

    return by_file, by_folder


def load_cache(cache_path):
    cache_file = Path(cache_path)
    if not cache_file.exists():
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache_path, payload):
    cache_file = Path(cache_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def build_cache_payload(archive_root, candidates):
    return {
        "archive_root": str(archive_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "remaining": candidates,
    }


def remove_cached_candidate(cache_path, archive_root, folder):
    payload = load_cache(cache_path)
    if not payload or payload.get("archive_root") != str(archive_root):
        return
    remaining = [item for item in payload.get("remaining", []) if item.get("folder") != str(folder)]
    payload["remaining"] = remaining
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_cache(cache_path, payload)


def iter_archive_folders(archive_root):
    archive_root = Path(archive_root)
    for user_dir in sorted(archive_root.iterdir()):
        if not user_dir.is_dir():
            continue
        for timestamp_dir in sorted(user_dir.iterdir()):
            if timestamp_dir.is_dir():
                yield timestamp_dir


def choose_video_file(folder):
    mp4_files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")
    if not mp4_files:
        return None

    normalized = [p for p in mp4_files if p.name.endswith("_normalized.mp4")]
    if len(normalized) == 1:
        return normalized[0]
    if len(mp4_files) == 1:
        return mp4_files[0]
    return normalized[0] if normalized else mp4_files[0]


def resolve_original_url(folder, video_path, file_index, folder_index):
    metadata_path = folder / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            original_url = metadata.get("original_url")
            if original_url:
                return original_url, "metadata"
        except Exception:
            pass

    rel_file = str(video_path.relative_to(folder.parents[1]))
    rel_folder = str(folder.relative_to(folder.parents[1]))

    file_keys = [rel_file, normalize_rel_key(rel_file), rel_file.replace("/", "\\")]
    folder_keys = [rel_folder, normalize_rel_key(rel_folder), rel_folder.replace("/", "\\")]

    for key in file_keys:
        if key in file_index:
            return file_index[key], "index:file"
    for key in folder_keys:
        if key in folder_index:
            return folder_index[key], "index:folder"

    return None, None


def has_audio_stream(path):
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
        return bool(probe.stdout.strip())
    except Exception:
        return True


def fresh_download_with_audio(url):
    vh = get_video_handler()
    temp_dir = Path(tempfile.mkdtemp(prefix="archive_audio_repair_"))
    try:
        log(f"  downloading: {url}")
        downloaded_path = vh.download_video(url, str(temp_dir))
        if not downloaded_path:
            raise vh.DownloadError("No video file was downloaded.")

        log(f"  normalizing: {downloaded_path}")
        final_path = vh.compress_video(downloaded_path, vh.MAX_SIZE_MB, force_normalize=True)
        has_audio = vh.has_audio_stream(final_path)
        return Path(final_path), has_audio, temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def replace_archived_video(target_path, repaired_path):
    temp_output = target_path.with_suffix(target_path.suffix + ".repairing")
    try:
        shutil.copy2(repaired_path, temp_output)
        os.replace(temp_output, target_path)
        return "atomic"
    except PermissionError:
        if temp_output.exists():
            try:
                temp_output.unlink()
            except Exception:
                pass
        shutil.copyfile(repaired_path, target_path)
        return "inplace"


def repair_entry(folder, video_path, url, apply_changes):
    repaired_path = None
    temp_dir = None
    try:
        log(f"[repair] {folder}")
        log(f"  target: {video_path.name}")
        repaired_path, has_audio, temp_dir = fresh_download_with_audio(url)
        if not has_audio:
            return "still_silent", "Fresh download still has no audio stream."
        if not apply_changes:
            return "repairable", f"Would replace with {repaired_path.name}"

        replace_mode = replace_archived_video(video_path, repaired_path)
        if replace_mode == "atomic":
            return "repaired", f"Replaced {video_path.name} via sibling temp swap"
        return "repaired", f"Replaced {video_path.name} via in-place SMB fallback"
    finally:
        if repaired_path and repaired_path.exists():
            try:
                repaired_path.unlink()
            except FileNotFoundError:
                pass
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def scan_candidates(archive_root, limit=None, verbose=False, include_ok=False):
    archive_root = Path(archive_root)
    file_index, folder_index = load_index_lookup(archive_root)
    results = []

    for count, folder in enumerate(iter_archive_folders(archive_root), start=1):
        if limit and count > limit:
            break
        if count == 1 or count % 25 == 0:
            log(f"Scanning folder {count}: {folder}")

        video_path = choose_video_file(folder)
        if not video_path:
            results.append({"folder": str(folder), "status": "no_video", "detail": "No .mp4 found"})
            continue

        if has_audio_stream(video_path):
            results.append({"folder": str(folder), "video": str(video_path), "status": "ok", "detail": "Audio present"})
            continue

        url, source = resolve_original_url(folder, video_path, file_index, folder_index)
        if not url:
            results.append(
                {
                    "folder": str(folder),
                    "video": str(video_path),
                    "status": "missing_url",
                    "detail": "Silent video but no original URL found",
                }
            )
            continue

        results.append(
            {
                "folder": str(folder),
                "video": str(video_path),
                "url": url,
                "url_source": source,
                "status": "candidate",
                "detail": "Silent video with resolved URL; run with --apply to attempt repair",
            }
        )

    print_report(results, apply_changes=False, verbose=verbose, include_ok=include_ok)
    return results


def load_or_refresh_candidates(archive_root, cache_path, limit=None, verbose=False, include_ok=False, refresh_cache=False):
    archive_root = Path(archive_root)
    payload = load_cache(cache_path)
    if not refresh_cache and payload and payload.get("archive_root") == str(archive_root):
        remaining = payload.get("remaining", [])
        log(f"Loaded {len(remaining)} cached repair candidate(s) from {cache_path}")
        return remaining

    log("Building repair candidate cache...")
    scan_results = scan_candidates(archive_root, limit=limit, verbose=verbose, include_ok=include_ok)
    candidates = [item for item in scan_results if item.get("status") == "candidate"]
    save_cache(cache_path, build_cache_payload(archive_root, candidates))
    log(f"Cached {len(candidates)} repair candidate(s) at {cache_path}")
    return candidates


def scan_archive(archive_root, apply_changes=False, limit=None, verbose=False, include_ok=False, cache_path=None, refresh_cache=False):
    archive_root = Path(archive_root)
    if not apply_changes:
        results = scan_candidates(archive_root, limit=limit, verbose=verbose, include_ok=include_ok)
        if cache_path:
            candidates = [item for item in results if item.get("status") == "candidate"]
            save_cache(cache_path, build_cache_payload(archive_root, candidates))
            log(f"Cached {len(candidates)} repair candidate(s) at {cache_path}")
        return results

    results = []
    log("Checking repair dependencies...")
    try:
        ensure_apply_dependencies()
    except Exception as e:
        log(f"Cannot run repairs: {e}")
        log("Install yt-dlp in this Python environment or run from the project virtualenv, then retry --apply.")
        return results

    candidates = load_or_refresh_candidates(
        archive_root,
        cache_path=cache_path,
        limit=limit,
        verbose=verbose,
        include_ok=include_ok,
        refresh_cache=refresh_cache,
    )
    if limit:
        candidates = candidates[:limit]

    total = len(candidates)
    for index, candidate in enumerate(candidates, start=1):
        folder = Path(candidate["folder"])
        video_path = Path(candidate["video"])
        log(f"Applying repair {index}/{total}: {folder}")
        try:
            status, detail = repair_entry(folder, video_path, candidate["url"], True)
        except Exception as e:
            status = "repair_failed"
            detail = str(e)
        result = dict(candidate)
        result["status"] = status
        result["detail"] = detail
        results.append(result)
        if status == "repaired":
            remove_cached_candidate(cache_path, archive_root, folder)
            log(f"  cache updated: removed {folder}")

    print_report(results, apply_changes=True, verbose=verbose, include_ok=include_ok)
    return results


def print_report(results, apply_changes=False, verbose=False, include_ok=False):
    summary = {
        "scanned": len(results),
        "ok": 0,
        "no_video": 0,
        "candidate": 0,
        "repairable": 0,
        "repaired": 0,
        "repair_failed": 0,
        "missing_url": 0,
        "still_silent": 0,
    }

    for item in results:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
        should_print = item["status"] != "ok" or include_ok or verbose
        if should_print:
            print(f"[{item['status']}] {item['folder']}")
            if "video" in item:
                print(f"  video: {item['video']}")
            if "url" in item:
                print(f"  url: {item['url']} ({item['url_source']})")
            print(f"  detail: {item['detail']}")

    mode = "apply" if apply_changes else "dry-run"
    print(f"\nMode: {mode}")
    print(f"Scanned folders: {summary['scanned']}")
    print(f"OK videos: {summary['ok']}")
    print(f"Silent candidates: {summary['candidate']}")
    print(f"Silent + repairable: {summary['repairable']}")
    print(f"Repaired: {summary['repaired']}")
    print(f"Repair failures: {summary['repair_failed']}")
    print(f"Silent + missing URL: {summary['missing_url']}")
    print(f"Silent + still silent after redownload: {summary['still_silent']}")
    print(f"Folders without video: {summary['no_video']}")


def main():
    args = parse_args()
    scan_archive(
        archive_root=args.archive_root,
        apply_changes=args.apply,
        limit=args.limit,
        verbose=args.verbose,
        include_ok=args.include_ok,
        cache_path=args.cache_path,
        refresh_cache=args.refresh_cache,
    )


if __name__ == "__main__":
    main()
