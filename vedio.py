# File name: analyze.py
import sys
import argparse
import time
import os
import json
import csv
import uuid
import subprocess
import shutil
import warnings
from datetime import datetime, timezone
from pathlib import Path
from prompts import DEFAULT_PROMPT

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

# Prefer the new Gemini SDK. Fall back to the deprecated one if needed.
_USING_NEW_GENAI = False
_GENAI_IMPORT_ERROR = None
types = None
genai = None
try:
    from google import genai as genai  # package: google-genai
    from google.genai import types

    _USING_NEW_GENAI = True
except Exception as new_err:
    try:
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            module=r"google\\.generativeai",
        )
        import google.generativeai as genai
    except Exception as old_err:
        _GENAI_IMPORT_ERROR = (new_err, old_err)

# load environment variables from .env
load_dotenv()

# It is recommended to set the KEY as an environment variable to avoid hardcoding it in the code.
# Note: API key is only required for LLM operations (single-file analysis / --process-llm).
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if genai is not None and (not _USING_NEW_GENAI):
    # Legacy SDK uses module-level configure(). New SDK uses Client(api_key=...).
    if API_KEY:
        genai.configure(api_key=API_KEY)


def _get_out_dir(cli_out_dir):
    env_out = os.getenv("VIDEO_JSON_DIR")
    if cli_out_dir:
        return Path(cli_out_dir)
    if env_out:
        return Path(env_out)
    return Path.cwd() / "video_jsons"


def load_existing_jsons(out_dir: Path):
    mapping = {}
    if out_dir.exists():
        for jf in out_dir.glob("*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    full = data.get("full_path")
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
        print(
            "Warning: 'ffprobe' not found on PATH (or FFPROBE_PATH not set). "
            "Media fields (duration/resolution/codec/etc.) will be set to null."
        )
        return {
            "duration_seconds": None,
            "width": None,
            "height": None,
            "resolution": None,
            "codec": None,
            "bitrate": None,
            "frame_rate": None,
        }
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

        frame_rate = None
        if vstream and vstream.get("r_frame_rate") and vstream.get("r_frame_rate") != "0/0":
            try:
                num, den = vstream.get("r_frame_rate").split("/")
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


def scan_directory(target_dir, out_dir: Path):
    exts = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv"}
    files = []
    for p in Path(target_dir).rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)

    out_dir.mkdir(parents=True, exist_ok=True)
    existing = load_existing_jsons(out_dir)
    rows = []

    for p in files:
        fp = str(p.resolve())

        if fp in existing:
            try:
                with open(existing[fp], "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    rows.append(
                        [
                            data.get("uuid"),
                            data.get("file_name"),
                            data.get("full_path"),
                            data.get("created_at"),
                            data.get("modified_at"),
                            data.get("size_bytes"),
                            data.get("duration_seconds"),
                            data.get("resolution"),
                            data.get("codec"),
                        ]
                    )
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
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, ensure_ascii=False, indent=2)

        rows.append(
            [
                record_uuid,
                metadata["file_name"],
                metadata["full_path"],
                metadata["created_at"],
                metadata["modified_at"],
                metadata["size_bytes"],
                metadata["duration_seconds"],
                metadata["resolution"],
                metadata["codec"],
            ]
        )

    csv_file = out_dir / "summary.csv"
    # Use UTF-8 with BOM so Excel on Windows opens it correctly.
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as cf:
        writer = csv.writer(cf)
        writer.writerow(
            [
                "uuid",
                "file_name",
                "full_path",
                "created_at",
                "modified_at",
                "size_bytes",
                "duration_seconds",
                "resolution",
                "codec",
            ]
        )
        for r in rows:
            writer.writerow(r)

    print(f"--> Scanned {len(rows)} files, summary saved to {csv_file}")
    return rows


def _extract_text_from_response(resp):
    text = getattr(resp, "text", None)
    if text:
        return text
    try:
        return resp.candidates[0].content.parts[0].text
    except Exception:
        return None


def _genai_upload(client, path):
    if _USING_NEW_GENAI:
        # google-genai has multiple incompatible upload signatures across versions.
        # Observed variants:
        # - upload(*, file=...)  (keyword-only; passing positional raises: takes 1 positional argument but 2 were given)
        # - upload(path=...)
        # - upload(<path>)
        upload_errors = []

        for attempt in (
            lambda: client.files.upload(file=path),
            lambda: client.files.upload(path=path),
            lambda: client.files.upload(path),
        ):
            try:
                return attempt()
            except TypeError as e:
                upload_errors.append(str(e))

        # Last resort: some versions accept a binary stream as `file=`.
        try:
            with open(path, "rb") as fh:
                return client.files.upload(file=fh)
        except TypeError as e:
            upload_errors.append(str(e))

        raise TypeError(
            "Unable to upload file with google-genai. Tried multiple signatures; last errors: "
            + " | ".join(upload_errors[-3:])
        )
    return genai.upload_file(path=path)


def _genai_get_file(client, name):
    if _USING_NEW_GENAI:
        return client.files.get(name=name)
    return genai.get_file(name)


def _genai_delete_file(client, name):
    if _USING_NEW_GENAI:
        return client.files.delete(name=name)
    return genai.delete_file(name)


def _file_state_name(file_obj):
    state = getattr(file_obj, "state", None)
    if state is None:
        return None
    if isinstance(state, str):
        return state
    return getattr(state, "name", None) or str(state)


def _genai_generate_text(client, video_file, prompt_text):
    if _USING_NEW_GENAI:
        model_name = os.getenv("GEMINI_MODEL") or "gemini-2.0-flash"
        uri = getattr(video_file, "uri", None)
        mime = getattr(video_file, "mime_type", None) or "video/mp4"
        if not uri:
            raise RuntimeError("Uploaded file missing uri")
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(uri=uri, mime_type=mime),
                    types.Part(text=prompt_text),
                ],
            )
        ]
        resp = client.models.generate_content(model=model_name, contents=contents)
        text = _extract_text_from_response(resp)
        return text or ""

    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL") or "models/gemini-flash-latest")
    resp = model.generate_content([video_file, prompt_text])
    return getattr(resp, "text", "")


def process_llm_on_jsons(out_dir: Path, prompt_text: str, client):
    existing = load_existing_jsons(out_dir)
    updated = 0
    for full_path, jf in existing.items():
        try:
            with open(jf, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception:
            continue
        if meta.get("response_text"):
            continue

        try:
            print(f"--> Uploading {meta.get('full_path')} for LLM analysis...")
            video_file = _genai_upload(client, meta.get("full_path"))

            while _file_state_name(video_file) == "PROCESSING":
                time.sleep(2)
                video_file = _genai_get_file(client, video_file.name)
            if _file_state_name(video_file) == "FAILED":
                print(f"--> Video processing failed: {meta.get('full_path')}")
                continue

            text = _genai_generate_text(client, video_file, prompt_text)
            meta["response_text"] = text
            with open(jf, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=2)

            _genai_delete_file(client, video_file.name)
            updated += 1
        except Exception as e:
            print(f"LLM processing failed for {meta.get('full_path')}: {e}")
            continue

    print(f"--> Updated {updated} JSON files with LLM responses")

def main():
    parser = argparse.ArgumentParser(description="Analyze a video file with Gemini and save results to JSON.")
    parser.add_argument("video_path", nargs="?", help="Path to video file")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="Prompt to send to the model")
    parser.add_argument("--out-dir", "-o", dest="out_dir", help="Directory to save JSON output. Can also be set via VIDEO_JSON_DIR env var. Defaults to ./video_jsons")
    parser.add_argument("--scan-dir", dest="scan_dir", help="Scan target directory for video files and create metadata JSONs + summary CSV (no LLM calls)")
    parser.add_argument("--process-llm", dest="process_llm", action="store_true", help="Process existing metadata JSONs by uploading files and adding LLM responses")
    args = parser.parse_args()

    video_path = args.video_path
    # Default prompt
    prompt = args.prompt

    out_dir = _get_out_dir(args.out_dir)

    client = None

    # batch modes
    if args.scan_dir:
        scan_directory(args.scan_dir, out_dir)
        return
    if args.process_llm:
        if genai is None:
            print(
                "錯誤：找不到 Gemini SDK。請安裝：pip install google-genai (或舊版 pip install google-generativeai)\n"
                f"Import errors: {_GENAI_IMPORT_ERROR}"
            )
            return
        if not API_KEY:
            print("錯誤：請先設定 GEMINI_API_KEY 環境變數 (需要用於 --process-llm)")
            return
        if _USING_NEW_GENAI:
            client = genai.Client(api_key=API_KEY)
        process_llm_on_jsons(out_dir, prompt, client)
        return

    if not video_path:
        print("錯誤：請提供 video_path，或使用 --scan-dir / --process-llm")
        return

    if not os.path.exists(video_path):
        print(f"錯誤：找不到檔案 {video_path}")
        return

    if not API_KEY:
        print("錯誤：請先設定 GEMINI_API_KEY 環境變數")
        return

    if genai is None:
        print(
            "錯誤：找不到 Gemini SDK。請安裝：pip install google-genai (或舊版 pip install google-generativeai)\n"
            f"Import errors: {_GENAI_IMPORT_ERROR}"
        )
        return

    if _USING_NEW_GENAI:
        client = genai.Client(api_key=API_KEY)

    print(f"--> 正在上傳 {video_path} 到雲端...")
    try:
        video_file = _genai_upload(client, video_path)
    except Exception as e:
        print(f"上傳失敗: {e}")
        return

    print("--> 等待影片處理中 (Processing)...")
    while _file_state_name(video_file) == "PROCESSING":
        time.sleep(2)
        video_file = _genai_get_file(client, video_file.name)

    if _file_state_name(video_file) == "FAILED":
        print("--> 影片處理失敗")
        return

    print("--> 開始分析...")
    try:
        response_text = _genai_generate_text(client, video_file, prompt)
    except Exception as e:
        print(f"分析失敗: {e}")
        return

    print("\n" + "=" * 30)
    print(response_text)
    print("=" * 30 + "\n")

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
        "response_text": response_text,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{record_uuid}.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    print(f"--> Saved analysis JSON to {out_file}")

    # Clean up remote file (recommended practice)
    _genai_delete_file(client, video_file.name)


if __name__ == "__main__":
    main()