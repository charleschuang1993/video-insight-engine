# File name: analyze.py
import sys
import time
import google.generativeai as genai
import os
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
    if len(sys.argv) < 2:
        print("用法: python analyze.py <影片路徑> [提示詞]")
        return

    video_path = sys.argv[1]
    # Default prompt
    prompt = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROMPT

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

    # Clean up remote file (recommended practice)
    genai.delete_file(video_file.name)


if __name__ == "__main__":
    main()