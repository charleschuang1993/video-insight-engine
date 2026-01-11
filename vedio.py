# File name: analyze.py
import sys
import argparse
import time
import google.generativeai as genai
import os
import json
import uuid
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from prompts import DEFAULT_PROMPT

# load environment variables from .env
load_dotenv()

# It is recommended to set the KEY as an environment variable to avoid hardcoding it in the code
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    print("錯誤：請先設定 GEMINI_API_KEY 環境變數")
    sys.exit(1)

genai.configure(api_key=API_KEY)

def main():
    parser = argparse.ArgumentParser(description="Analyze a video file with Gemini and save results to JSON.")
    parser.add_argument("video_path", help="Path to video file")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="Prompt to send to the model")
    parser.add_argument("--out-dir", "-o", dest="out_dir", help="Directory to save JSON output. Can also be set via VIDEO_JSON_DIR env var. Defaults to ./video_jsons")
    args = parser.parse_args()

    video_path = args.video_path
    # Default prompt
    prompt = args.prompt

    if not os.path.exists(video_path):
        print(f"錯誤：找不到檔案 {video_path}")
        return

    print(f"--> 正在上傳 {video_path} 到雲端...")
    try:
        video_file = genai.upload_file(path=video_path)
    except Exception as e:
        print(f"上傳失敗: {e}")
        return

    print("--> 等待影片處理中 (Processing)...")
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        print("--> 影片處理失敗")
        return

    print("--> 開始分析...")
    model = genai.GenerativeModel("models/gemini-flash-latest")  # Flash model: faster and cheaper
    response = model.generate_content([video_file, prompt])

    print("\n" + "=" * 30)
    print(response.text)
    print("=" * 30 + "\n")

    # Prepare metadata/schema for video management and save to JSON
    def get_video_duration(path):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            print("Error: 'ffprobe' not found on PATH. Please install ffmpeg/ffprobe and ensure ffprobe is available in your PATH. For Windows, try: 'choco install ffmpeg' or 'winget install --id Gyan.FFmpeg'.")
            sys.exit(1)
        try:
            # run ffprobe to get duration in seconds
            res = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(res.stdout.strip()) if res.stdout else None
        except Exception:
            print("Warning: failed to get duration via ffprobe; proceeding with duration=None")
            return None

    file_path = os.path.abspath(video_path)
    stat = os.stat(file_path)
    created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
    modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
    size_bytes = stat.st_size
    duration_seconds = get_video_duration(file_path)

    record_uuid = str(uuid.uuid4())
    metadata = {
        "uuid": record_uuid,
        "file_name": os.path.basename(file_path),
        "full_path": file_path,
        "created_at": created_at,
        "modified_at": modified_at,
        "size_bytes": size_bytes,
        "duration_seconds": duration_seconds,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "response_text": response.text,
    }

    env_out = os.getenv("VIDEO_JSON_DIR")
    if args.out_dir:
        out_dir = Path(args.out_dir)
    elif env_out:
        out_dir = Path(env_out)
    else:
        out_dir = Path.cwd() / "video_jsons"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{record_uuid}.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    print(f"--> Saved analysis JSON to {out_file}")

    # Clean up remote file (recommended practice)
    genai.delete_file(video_file.name)


if __name__ == "__main__":
    main()