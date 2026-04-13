# Test Gap TODOs

1. `video_handler` subtitle fallback error routing
- Add a test that non-subtitle `CalledProcessError` is re-raised and not retried without subtitle flags.

2. `video_handler` cleanup safety
- Add a test that `_remove_new_files` does not delete pre-existing files in `output_dir` when a selector attempt fails or returns silent media.

3. `bot` compatibility matcher coverage
- Add parametrized stderr tests for `HTTP 426`, `IncompatibleClassChangeError`, `NoSuchMethodError`, and case variants.

4. `bot` false-positive guard
- Add a test for benign stderr lines containing words like `version` that must not trigger update guidance or shutdown.

5. `repair_silent_archives` lookup precedence
- Add a test where both normalized file-level and folder-level index matches exist; assert `index:file` wins.

6. `repair_silent_archives` cache key normalization
- Add a test that `remove_cached_candidate` works when cache folder keys use mixed slash styles.

7. Docker build contract smoke check
- Add CI smoke checks validating:
  - `java -version` major is `25`
  - `signal-cli --version` is non-empty
