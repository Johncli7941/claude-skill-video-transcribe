# Workflow: Transcribe

将视频/音频转成完整文字稿。

---

## 判断输入类型

### A. 用户给的是本地文件路径

```bash
python3 ~/.shared-skills/VideoTranscribe/Tools/transcribe.py \
  --input "/path/to/video.mp4" \
  --engine gemini          # 默认 gemini（有标点）；改 mlx 用本地离线
```

### B. 用户给的是 URL（YouTube / B站 / 其他）

```bash
python3 ~/.shared-skills/VideoTranscribe/Tools/transcribe.py \
  --input "https://www.youtube.com/watch?v=xxxxx" \
  --engine gemini
```

脚本自动判断：
1. 先用 yt-dlp 尝试抓现成字幕（最快，0 API 消耗）
2. 字幕不存在 → 下载音频 → Gemini 转录
3. Gemini 不可用 → fallback 到 mlx-whisper 本地

---

## 执行后

1. 转录结果自动保存到 `~/Downloads/transcript_YYYYMMDD_HHMMSS.txt`
2. 向用户展示前 500 字预览
3. 告知文件路径
4. 询问："需要我进一步提炼核心要点吗？"

---

## 引擎说明

| 引擎 | 命令 | 优点 | 缺点 |
|------|------|------|------|
| `gemini`（默认）| `--engine gemini` | 有标点、可读性好 | 需网络 + API Key |
| `mlx` | `--engine mlx` | 完全离线、免费 | 无标点、首次下载模型慢 |
