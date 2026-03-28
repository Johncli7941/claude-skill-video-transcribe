#!/usr/bin/env python3
"""
VideoTranscribe — 视频/音频转文字工具
支持：本地文件、YouTube、B站、任何 yt-dlp 支持的平台
引擎：gemini（默认，有标点）/ mlx（本地离线，无标点）

用法：
  python3 transcribe.py --input "video.mp4"
  python3 transcribe.py --input "https://youtu.be/xxx"
  python3 transcribe.py --input "https://www.bilibili.com/video/BVxxx"
  python3 transcribe.py --input "video.mp4" --engine mlx
  python3 transcribe.py --input "video.mp4" --output ~/Desktop/result.txt
"""

import argparse
import os
import sys
import subprocess
import tempfile
import pathlib
from datetime import datetime

# ─── 工具函数 ─────────────────────────────────────────────

def is_url(text):
    return text.startswith(("http://", "https://", "www."))

def timestamp_filename(prefix="transcript", ext="txt"):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.{ext}"

def get_api_key():
    """从 api-registry 读取 GEMINI_API_KEY"""
    env_file = os.path.expanduser("~/.shared-skills/api-registry/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("GEMINI_API_KEY", "")

# ─── 字幕抓取（URL 优先路径）────────────────────────────────

def try_fetch_subtitles(url, tmpdir):
    """
    用 yt-dlp 尝试抓取现成字幕（.vtt / .srt / .json3）
    成功返回字幕文本，失败返回 None
    """
    print("🔍 尝试抓取现成字幕...", flush=True)
    sub_path = os.path.join(tmpdir, "subtitle")

    # 先尝试自动生成字幕（YouTube auto-subtitle），再尝试官方字幕
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", "zh-Hans,zh,zh-Hant,en",
        "--sub-format", "vtt/srt/best",
        "--skip-download",
        "--no-playlist",
        "-o", sub_path,
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # 找下载下来的字幕文件
    for fname in os.listdir(tmpdir):
        fpath = os.path.join(tmpdir, fname)
        if fname.startswith("subtitle") and (fname.endswith(".vtt") or fname.endswith(".srt")):
            text = parse_subtitle_file(fpath)
            if text and len(text) > 100:
                print(f"✅ 字幕抓取成功（{len(text)} 字）", flush=True)
                return text

    print("⚠️  无现成字幕，改用音频转录...", flush=True)
    return None

def parse_subtitle_file(fpath):
    """解析 VTT / SRT 字幕，去掉时间戳，返回纯文本"""
    lines = []
    with open(fpath, encoding="utf-8", errors="ignore") as f:
        content = f.read()

    import re
    # 去掉 VTT header
    content = re.sub(r"WEBVTT.*?\n\n", "", content, flags=re.DOTALL)
    # 去掉时间戳行（如 00:00:01.000 --> 00:00:03.000）
    content = re.sub(r"\d{1,2}:\d{2}:\d{2}[\.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[\.,]\d{3}.*?\n", "", content)
    # 去掉序号行
    content = re.sub(r"^\d+\s*$", "", content, flags=re.MULTILINE)
    # 去掉 HTML 标签
    content = re.sub(r"<[^>]+>", "", content)
    # 合并连续空行
    content = re.sub(r"\n{3,}", "\n\n", content)

    # 去重相邻重复行（VTT 经常有滚动重复）
    seen = set()
    result = []
    for line in content.split("\n"):
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            result.append(line)

    return " ".join(result).strip()

# ─── 音频下载 ────────────────────────────────────────────

def download_audio(url, tmpdir):
    """用 yt-dlp 下载音频为 mp3"""
    print("⬇️  下载音频中...", flush=True)
    audio_path = os.path.join(tmpdir, "audio.mp3")
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "32K",
        "--no-playlist",
        "-o", audio_path,
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 下载失败：{result.stderr[-500:]}")
    if not os.path.exists(audio_path):
        raise RuntimeError("音频文件未找到，下载可能失败")
    size_mb = os.path.getsize(audio_path) / 1024 / 1024
    print(f"✅ 音频下载完成（{size_mb:.1f} MB）", flush=True)
    return audio_path

def extract_audio_from_local(input_path, tmpdir):
    """用 ffmpeg 从本地视频提取音频"""
    ext = os.path.splitext(input_path)[1].lower()
    # 如果本身就是音频，直接用
    if ext in (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"):
        return input_path
    print("🎵 提取音频中...", flush=True)
    audio_path = os.path.join(tmpdir, "audio.mp3")
    cmd = ["ffmpeg", "-i", input_path, "-vn", "-ar", "16000", "-ac", "1", "-ab", "32k", "-f", "mp3", audio_path, "-y"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 提取音频失败：{result.stderr[-300:]}")
    return audio_path

# ─── 转录引擎：Gemini ───────────────────────────────────

def transcribe_gemini(audio_path):
    """用 Gemini 2.5 Flash 转录，结果有标点"""
    try:
        import google.genai as genai
    except ImportError:
        print("📦 安装 google-genai...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "google-genai"], check=True)
        import google.genai as genai

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("找不到 GEMINI_API_KEY，请检查 ~/.shared-skills/api-registry/.env")

    print("☁️  Gemini 转录中（有标点）...", flush=True)
    client = genai.Client(api_key=api_key)
    audio_file = client.files.upload(file=pathlib.Path(audio_path))
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            audio_file,
            "请将这段音频完整逐字转录成文字。如果是中文就输出中文，如果是英文就输出英文。"
            "不要总结，保留原话，包括语气词和口语表达。"
        ]
    )
    return response.text

# ─── 转录引擎：mlx-whisper（本地）────────────────────────

def transcribe_mlx(audio_path):
    """用 mlx-whisper 本地转录，无标点"""
    try:
        import mlx_whisper
    except ImportError:
        raise RuntimeError("mlx-whisper 未安装，请运行：pip3 install mlx-whisper")

    print("🖥️  本地 mlx-whisper 转录中（无标点，首次需下载模型）...", flush=True)
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo="mlx-community/whisper-turbo",
        language=None,   # 自动检测语言
        verbose=False
    )
    return result["text"]

# ─── 主流程 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="视频/音频 → 文字转录工具")
    parser.add_argument("--input", "-i", required=True, help="本地文件路径或视频 URL")
    parser.add_argument("--engine", "-e", choices=["gemini", "mlx"], default="gemini",
                        help="转录引擎（gemini=有标点 API，mlx=本地离线）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 ~/Downloads/transcript_时间戳.txt）")
    parser.add_argument("--no-subtitle", action="store_true", help="跳过字幕抓取，直接转录")
    args = parser.parse_args()

    # 输出路径
    if args.output:
        output_path = os.path.expanduser(args.output)
    else:
        output_path = os.path.expanduser(f"~/Downloads/{timestamp_filename()}")

    with tempfile.TemporaryDirectory() as tmpdir:
        text = None

        if is_url(args.input):
            # ── URL 路径 ──
            print(f"🌐 识别为 URL：{args.input}", flush=True)

            # Step 1: 尝试抓字幕
            if not args.no_subtitle:
                text = try_fetch_subtitles(args.input, tmpdir)

            # Step 2: 字幕不存在，下载音频转录
            if not text:
                audio_path = download_audio(args.input, tmpdir)
                if args.engine == "gemini":
                    text = transcribe_gemini(audio_path)
                else:
                    text = transcribe_mlx(audio_path)

        else:
            # ── 本地文件路径 ──
            input_path = os.path.expanduser(args.input)
            if not os.path.exists(input_path):
                print(f"❌ 文件不存在：{input_path}", file=sys.stderr)
                sys.exit(1)

            print(f"📁 本地文件：{input_path}", flush=True)
            audio_path = extract_audio_from_local(input_path, tmpdir)

            if args.engine == "gemini":
                text = transcribe_gemini(audio_path)
            else:
                text = transcribe_mlx(audio_path)

    # 写出结果
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\n✅ 转录完成！")
    print(f"📄 文件已保存：{output_path}")
    print(f"📊 字数：{len(text)} 字")
    print(f"\n── 前 300 字预览 ──")
    print(text[:300])
    if len(text) > 300:
        print("...")

if __name__ == "__main__":
    main()
