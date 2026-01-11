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
