#!/usr/bin/env python3
"""YouTube 字幕优先提取 — 比 Whisper 转录快 10 倍"""

from logger import log


def fetch_youtube_transcript(
    url: str, language: str | None = None,
) -> str | None:
    """用 youtube-transcript-api 抓字幕，成功返回文本，失败返回 None"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        import urllib.parse

        # 提取 video_id
        u = urllib.parse.urlparse(url)
        if "youtu.be" in (u.hostname or ""):
            video_id = u.path.lstrip("/")
        else:
            video_id = urllib.parse.parse_qs(u.query).get("v", [""])[0]

        if not video_id:
            return None

        log(f"  YouTube subtitles: {video_id}")

        # 优先语言
        lang_prefs = []
        if language and language != "auto":
            lang_prefs.append(language)
        lang_prefs.extend(["zh-Hans", "zh-Hant", "zh", "en"])

        ytt = YouTubeTranscriptApi()
        transcript_data = ytt.fetch(video_id, languages=lang_prefs)

        lines = []
        for entry in transcript_data:
            m, s = divmod(int(entry.start), 60)
            ts = f"{m:02d}:{s:02d}"
            lines.append(f"[{ts}] {entry.text}")

        text = "\n".join(lines)
        if len(text) < 50:
            log("  Subtitles too short, skipping")
            return None

        log(f"  YouTube subtitles OK: {len(text)} chars")
        return text

    except Exception as e:
        log(f"  YouTube subtitles failed ({e}), falling back to Whisper")
        return None
