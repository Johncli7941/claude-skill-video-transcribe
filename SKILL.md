---
name: VideoTranscribe
description: 视频/音频转文字 + 核心提炼。USE WHEN 用户提到：转录、转文字、字幕、视频转文字、音频转文字、抓字幕、YouTube转文字、B站转文字、视频笔记、transcript、提炼视频重点、视频总结。
---

# VideoTranscribe

将视频/音频内容转成文字，并可进一步提炼核心要点。

支持：
- **本地文件**：MP4、MOV、MP3、M4A 等
- **在线 URL**：YouTube、B站、小宇宙、优酷等 yt-dlp 支持的平台
- **提炼模式**：转录完成后可输出结构化要点摘要

## 🔊 Voice Notification（必须先执行）

```bash
curl -s -X POST http://localhost:8888/notify \
  -H "Content-Type: application/json" \
  -d '{"message": "Running VideoTranscribe skill"}' > /dev/null 2>&1 &
```

## Workflow Routing

| 用户说的 | 路由到 |
|---------|--------|
| 转录 / 转文字 / 字幕 / 发来视频文件或URL | `Workflows/Transcribe.md` |
| 提炼 / 总结 / 核心要点 / 重点 | `Workflows/Extract.md` |
| 两者都要（先转再提炼）| 先 `Transcribe.md`，再 `Extract.md` |

## Quick Reference

- 脚本路径：`~/.shared-skills/VideoTranscribe/Tools/transcribe.py`
- 优先策略：URL → 抓字幕（快）→ 无字幕则下音频转录
- 转录引擎：Gemini 2.5 Flash（有标点） / mlx-whisper（离线备选）
- 输出默认存：`~/Downloads/transcript_YYYYMMDD_HHMMSS.txt`
