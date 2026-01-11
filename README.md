# Video Insight Engine

Analyze video files and save per-video JSON metadata/results (one JSON per video, named by UUID).

Quick start

- Run the script:

```powershell
python vedio.py C:\path\to\video.mp4 --out-dir C:\path\to\jsons
```

- Output: each analysis is saved as `<uuid>.json` in the specified directory (default `./video_jsons`).

Notes

- The script records filesystem metadata (file name, full path, size, created/modified times) and stores the model `response_text` in the JSON.
- The script uses `ffprobe` to obtain accurate media duration. If you need detailed install instructions, see INSTALL.md.
- You can configure the JSON output directory with `--out-dir` or the `VIDEO_JSON_DIR` environment variable.
- If you prefer not to modify PATH, you can pass a specific `ffprobe` binary path by setting the `FFPROBE_PATH` environment variable or requesting the `--ffprobe-path` option (if enabled).

For platform-specific ffmpeg/ffprobe installation and troubleshooting, see INSTALL.md.

## Usage examples

Single-file analysis (default):

```powershell
python vedio.py C:\path\to\video.mp4 --out-dir C:\path\to\jsons
```

Scan a directory (create metadata JSONs and summary CSV; no LLM calls):

```powershell
python vedio.py dummy_path --scan-dir C:\path\to\videos --out-dir C:\path\to\jsons
```

Note: the script requires a positional `video_path` argument but `--scan-dir` triggers directory scanning; the `video_path` can be any placeholder when using `--scan-dir`.

Process existing metadata JSONs and append LLM responses:

```powershell
python vedio.py dummy_path --process-llm --out-dir C:\path\to\jsons
```

Environment variables:

- `VIDEO_JSON_DIR`: alternative to `--out-dir`.
- `FFPROBE_PATH`: specify the full path to the `ffprobe` binary if it's not on PATH.

Output:

- Per-video metadata JSONs named `<uuid>.json` are written to the `out-dir` (fields include `uuid`, `file_name`, `full_path`, `size_bytes`, `duration_seconds`, `resolution`, `codec`, `frame_rate`, and `response_text`).
- `summary.csv` (created by `--scan-dir`) lists basic info for all discovered videos.
