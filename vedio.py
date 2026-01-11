# File name: analyze.py
import sys
import argparse
import time
import google.generativeai as genai
import os
import json
import csv
import uuid
import subprocess
import shutil
from datetime import datetime, timezone
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
    parser.add_argument("--scan-dir", dest="scan_dir", help="Scan target directory for video files and create metadata JSONs + summary CSV (no LLM calls)")
    parser.add_argument("--process-llm", dest="process_llm", action="store_true", help="Process existing metadata JSONs by uploading files and adding LLM responses")
    args = parser.parse_args()

    video_path = args.video_path
    # Default prompt
    prompt = args.prompt

    # determine output directory early (used by scan/process modes)
    env_out = os.getenv("VIDEO_JSON_DIR")
    if args.out_dir:
        out_dir = Path(args.out_dir)
    elif env_out:
        out_dir = Path(env_out)
    else:
        out_dir = Path.cwd() / "video_jsons"

    # batch modes
    if args.scan_dir:
        scan_directory(args.scan_dir, out_dir)
        return
    if args.process_llm:
        process_llm_on_jsons(out_dir, prompt)
        return

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
    def load_existing_jsons(out_dir):
        mapping = {}
        if out_dir.exists():
            for jf in out_dir.glob('*.json'):
                try:
                    with open(jf, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                        full = data.get('full_path')
                        if full:
                            mapping[os.path.abspath(full)] = jf
                except Exception:
                    continue
        return mapping

    def get_media_info(path):
        """Return media info dict using ffprobe JSON output.

        Fields: duration_seconds, width, height, resolution, codec, bitrate, frame_rate
        """
        ffprobe = os.getenv("FFPROBE_PATH") or shutil.which("ffprobe")
        if not ffprobe:
            print("Error: 'ffprobe' not found on PATH. Please install ffmpeg/ffprobe and ensure ffprobe is available in your PATH. For Windows, try: 'choco install ffmpeg' or 'winget install --id Gyan.FFmpeg'.")
            sys.exit(1)
        try:
            res = subprocess.run(
                [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            info = json.loads(res.stdout)
            fmt = info.get("format", {})
            streams = info.get("streams", [])
            # find first video stream
            vstream = None
            for s in streams:
                if s.get("codec_type") == "video":
                    vstream = s
                    break

            duration = None
            try:
                if fmt.get("duration"):
                    duration = float(fmt.get("duration"))
            except Exception:
                duration = None

            width = int(vstream.get("width")) if vstream and vstream.get("width") else None
            height = int(vstream.get("height")) if vstream and vstream.get("height") else None
            resolution = f"{width}x{height}" if width and height else None
            codec = vstream.get("codec_name") if vstream else None

            # bitrate: prefer stream, fallback to format
            bit_rate = None
            if vstream and vstream.get("bit_rate"):
                try:
                    bit_rate = int(vstream.get("bit_rate"))
                except Exception:
                    bit_rate = None
            elif fmt.get("bit_rate"):
                try:
                    bit_rate = int(fmt.get("bit_rate"))
                except Exception:
                    bit_rate = None

            # frame rate: r_frame_rate like '30000/1001'
            frame_rate = None
            if vstream and vstream.get("r_frame_rate") and vstream.get("r_frame_rate") != "0/0":
                try:
                    num, den = vstream.get("r_frame_rate").split('/')
                    frame_rate = float(num) / float(den) if float(den) != 0 else None
                except Exception:
                    frame_rate = None

            return {
                "duration_seconds": duration,
                "width": width,
                "height": height,
                "resolution": resolution,
                "codec": codec,
                "bitrate": bit_rate,
                "frame_rate": frame_rate,
            }
        except Exception:
            print("Warning: failed to get media info via ffprobe; proceeding with limited metadata")
            return {
                "duration_seconds": None,
                "width": None,
                "height": None,
                "resolution": None,
                "codec": None,
                "bitrate": None,
                "frame_rate": None,
            }

    # scan a directory and create metadata jsons + summary csv
    def scan_directory(target_dir, out_dir):
        exts = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.flv'}
        files = []
        for p in Path(target_dir).rglob('*'):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)

        out_dir.mkdir(parents=True, exist_ok=True)
        existing = load_existing_jsons(out_dir)
        rows = []
        for p in files:
            fp = str(p.resolve())
            # if already have json for this path, skip creating a new uuid
            if fp in existing:
                try:
                    with open(existing[fp], 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                        rows.append([
                            data.get('uuid'), data.get('file_name'), data.get('full_path'), data.get('created_at'),
                            data.get('modified_at'), data.get('size_bytes'), data.get('duration_seconds'), data.get('resolution'), data.get('codec')
                        ])
                    continue
                except Exception:
                    pass

            stat = os.stat(fp)
            created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
            modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
            size_bytes = stat.st_size
            media_info = get_media_info(fp)
            record_uuid = str(uuid.uuid4())
            metadata = {
                "uuid": record_uuid,
                "file_name": os.path.basename(fp),
                "full_path": fp,
                "created_at": created_at,
                "modified_at": modified_at,
                "size_bytes": size_bytes,
                "duration_seconds": media_info.get("duration_seconds"),
                "width": media_info.get("width"),
                "height": media_info.get("height"),
                "resolution": media_info.get("resolution"),
                "codec": media_info.get("codec"),
                "bitrate": media_info.get("bitrate"),
                "frame_rate": media_info.get("frame_rate"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "response_text": None,
            }
            out_file = out_dir / f"{record_uuid}.json"
            with open(out_file, 'w', encoding='utf-8') as fh:
                json.dump(metadata, fh, ensure_ascii=False, indent=2)
            rows.append([
                record_uuid, metadata['file_name'], metadata['full_path'], metadata['created_at'],
                metadata['modified_at'], metadata['size_bytes'], metadata['duration_seconds'], metadata['resolution'], metadata['codec']
            ])

        # write summary CSV
        csv_file = out_dir / 'summary.csv'
        with open(csv_file, 'w', newline='', encoding='utf-8') as cf:
            writer = csv.writer(cf)
            writer.writerow(['uuid','file_name','full_path','created_at','modified_at','size_bytes','duration_seconds','resolution','codec'])
            for r in rows:
                writer.writerow(r)

        print(f"--> Scanned {len(rows)} files, summary saved to {csv_file}")
        return rows

    # process existing metadata jsons by calling LLM and appending response_text
    def process_llm_on_jsons(out_dir, prompt):
        out_dir = Path(out_dir)
        existing = load_existing_jsons(out_dir)
        updated = 0
        for full_path, jf in existing.items():
            try:
                with open(jf, 'r', encoding='utf-8') as fh:
                    meta = json.load(fh)
            except Exception:
                continue
            # skip if response already present
            if meta.get('response_text'):
                continue
            # upload and call model
            try:
                print(f"--> Uploading {meta.get('full_path')} for LLM analysis...")
                video_file = genai.upload_file(path=meta.get('full_path'))
                model = genai.GenerativeModel("models/gemini-flash-latest")
                response = model.generate_content([video_file, prompt])
                meta['response_text'] = response.text
                # write back
                with open(jf, 'w', encoding='utf-8') as fh:
                    json.dump(meta, fh, ensure_ascii=False, indent=2)
                genai.delete_file(video_file.name)
                updated += 1
            except Exception as e:
                print(f"LLM processing failed for {meta.get('full_path')}: {e}")
                continue

        print(f"--> Updated {updated} JSON files with LLM responses")

    file_path = os.path.abspath(video_path)
    stat = os.stat(file_path)
    created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
    modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
    size_bytes = stat.st_size
    media_info = get_media_info(file_path)

    record_uuid = str(uuid.uuid4())
    metadata = {
        "uuid": record_uuid,
        "file_name": os.path.basename(file_path),
        "full_path": file_path,
        "created_at": created_at,
        "modified_at": modified_at,
        "size_bytes": size_bytes,
        "duration_seconds": media_info.get("duration_seconds"),
        "width": media_info.get("width"),
        "height": media_info.get("height"),
        "resolution": media_info.get("resolution"),
        "codec": media_info.get("codec"),
        "bitrate": media_info.get("bitrate"),
        "frame_rate": media_info.get("frame_rate"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "response_text": response.text,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{record_uuid}.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    print(f"--> Saved analysis JSON to {out_file}")

    # Clean up remote file (recommended practice)
    genai.delete_file(video_file.name)


if __name__ == "__main__":
    main()