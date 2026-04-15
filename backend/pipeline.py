#!/usr/bin/env python3
"""
核心处理管道

inbox/ 文件 → 等待就绪 → 去重检查 → 视频提取音频 → 转录 →
质量检查 → Claude 分类+标题+总结 → 写入 Obsidian → 归档
"""

import json
import os
import platform
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from filelock import FileLock, Timeout

from config import Config
from dedup import DedupDB
from logger import log
from notifier import notify, notify_telegram
from summarizer import AnalysisResult, Summarizer, TYPE_TAGS, VALID_SCENES
from transcriber import (
    ALL_EXTENSIONS,
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    Transcriber,
    check_transcript_quality,
    extract_audio,
    get_audio_duration,
)


@dataclass(frozen=True)
class ProcessResult:
    """处理结果"""
    filename: str
    scene: str
    title: str
    duration_sec: float
    note_path: str
    source: str


class Pipeline:
    """核心处理管道"""

    def __init__(self, config: Config):
        self.config = config
        self.db = DedupDB(config.db_path)
        self.transcriber: Transcriber | None = None  # 延迟加载（模型大）
        self.summarizer = Summarizer(
            prompts_dir=config.prompts_dir,
            timeout=config.claude_timeout,
            max_retries=config.claude_max_retries,
            max_chars=config.max_transcript_chars,
        )
        self._lock = FileLock(str(config.base_dir / ".process.lock"), timeout=0)
        self.paused = False

        # 事件回调 (UI 通过 WebSocket 监听)
        self.on_progress: Callable[[str, str, dict], None] | None = None

    def _ensure_dirs(self) -> None:
        """确保工作目录存在"""
        for d in (
            self.config.inbox_dir,
            self.config.processing_dir,
            self.config.done_dir,
            self.config.failed_dir,
            self.config.transcripts_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def _ensure_transcriber(self) -> Transcriber:
        """延迟加载转录模型"""
        if self.transcriber is None:
            log(f"Loading Whisper model: {self.config.whisper_model} ({self.config.whisper_device})")
            self.transcriber = Transcriber(
                model_name=self.config.whisper_model,
                device=self.config.whisper_device,
                language=self.config.whisper_language,
                cpu_threads=self.config.whisper_threads,
            )
        return self.transcriber

    def _emit(self, step: str, filename: str, **kwargs: object) -> None:
        """发送进度事件"""
        if self.on_progress:
            self.on_progress(step, filename, kwargs)

    def process_inbox(self) -> list[ProcessResult]:
        """扫描 inbox/ 处理所有待处理文件"""
        self._ensure_dirs()
        self.db.mark_stale_jobs()

        # 恢复 processing/ 中的孤儿文件
        self._recover_orphans()

        try:
            self._lock.acquire()
        except Timeout:
            log("Another instance is running, skipping")
            return []

        results = []
        try:
            _lower_priority(self.config.process_priority)

            for file_path in self._scan_inbox():
                if self.paused:
                    log("Paused, stopping processing")
                    break
                result = self.process_file(file_path)
                if result:
                    results.append(result)
        finally:
            self._lock.release()

        return results

    def process_file(
        self,
        file_path: Path,
        source: str = "manual",
        meta: dict | None = None,
    ) -> ProcessResult | None:
        """处理单个文件"""
        log(f"Processing: {file_path.name}")
        job_id = self.db.add_job(file_path.name)
        meta = meta or {}

        try:
            # 1. 等待文件就绪
            ready_path = _wait_for_file_ready(
                file_path, self.config.file_stable_seconds,
            )
            if not ready_path:
                self.db.update_job(job_id, "failed", error="File disappeared")
                return None

            # 2. 去重检查
            content_hash = DedupDB.file_hash(ready_path)
            if self.db.is_duplicate(ready_path):
                log(f"  Skipping (duplicate): {ready_path.name}")
                shutil.move(str(ready_path), str(self.config.done_dir / ready_path.name))
                self.db.update_job(job_id, "done", note_name="(duplicate)")
                return None
            self.db.update_job(job_id, "waiting", content_hash=content_hash)

            # 3. 移到 processing/
            proc_path = self.config.processing_dir / ready_path.name
            shutil.move(str(ready_path), str(proc_path))

            # 同名 .meta sidecar 也移过去
            meta_file = ready_path.with_suffix(ready_path.suffix + ".meta")
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                shutil.move(str(meta_file), str(self.config.processing_dir / meta_file.name))

            # 4. 提取音频 (如果是视频)
            self._emit("extracting", proc_path.name)
            self.db.update_job(job_id, "extracting")
            audio_path = proc_path
            if proc_path.suffix.lower() in VIDEO_EXTENSIONS:
                audio_path = extract_audio(proc_path)

            # 获取时长
            duration = get_audio_duration(audio_path)
            self.db.update_job(job_id, "extracting", duration_sec=duration)

            # 5. YouTube 字幕优先
            transcript_text = None
            source_url = meta.get("url", "")
            platform_name = meta.get("platform", "")
            is_ad = meta.get("is_ad", False)
            language = meta.get("language")

            if platform_name and "youtube" in platform_name:
                transcript_text = _try_youtube_subtitles(source_url, language)

            # 6. 转录
            if not transcript_text:
                self._emit("transcribing", proc_path.name)
                self.db.update_job(job_id, "transcribing")
                transcriber = self._ensure_transcriber()
                result = transcriber.transcribe(audio_path, language=language)
                transcript_text = result.text
                duration = result.duration or duration

                # 质量检查
                ok, reason = check_transcript_quality(result.raw_text, duration)
                if not ok:
                    log(f"  Quality check failed: {reason}")
                    log("  Retrying with language=auto...")
                    result2 = transcriber.transcribe(audio_path, language="auto")
                    ok2, _ = check_transcript_quality(result2.raw_text, duration)
                    if ok2 and len(result2.raw_text) > len(result.raw_text):
                        transcript_text = result2.text

            # 保存转录备份
            transcript_backup = self.config.transcripts_dir / f"{proc_path.stem}.txt"
            transcript_backup.write_text(transcript_text)

            # 7. Claude 分类+标题+总结
            self._emit("summarizing", proc_path.name)
            self.db.update_job(job_id, "summarizing")
            analysis = self.summarizer.analyze(
                transcript_text,
                platform=platform_name,
                duration_sec=duration,
                is_ad=is_ad,
            )

            # 8. 写入 Obsidian
            self._emit("saving", proc_path.name)
            self.db.update_job(job_id, "saving")
            note_path = _write_obsidian_note(
                config=self.config,
                analysis=analysis,
                transcript=transcript_text,
                source_name=proc_path.name,
                duration_sec=duration,
                source_url=source_url,
                platform=platform_name,
                is_ad=is_ad,
            )

            # 9. 去重标记 + 归档
            self.db.mark_processed(proc_path, source, str(note_path))
            shutil.move(str(proc_path), str(self.config.done_dir / proc_path.name))

            # 清理视频提取的临时音频
            if audio_path != proc_path and audio_path.exists():
                audio_path.unlink()

            self.db.update_job(
                job_id, "done",
                note_name=note_path.name,
                duration_sec=duration,
            )
            self._emit("done", proc_path.name, note_path=str(note_path))

            # 通知
            notify("Auto-Transcribe", f"Done: {analysis.title or proc_path.name}")
            tg_chat = meta.get("chat_id")
            if tg_chat:
                notify_telegram(
                    self.config.telegram_bot_token,
                    tg_chat,
                    f"✅ {analysis.title or proc_path.name}\n📝 {analysis.scene}",
                )

            log(f"  Done: {note_path.name}")
            return ProcessResult(
                filename=proc_path.name,
                scene=analysis.scene,
                title=analysis.title,
                duration_sec=duration,
                note_path=str(note_path),
                source=source,
            )

        except Exception as e:
            log(f"  FAILED: {e}")
            self.db.update_job(job_id, "failed", error=str(e))
            self._emit("failed", file_path.name, error=str(e))
            # 移到 failed/
            if proc_path.exists():
                shutil.move(str(proc_path), str(self.config.failed_dir / proc_path.name))
            return None

    def _scan_inbox(self) -> list[Path]:
        """扫描 inbox/ 中的音视频文件"""
        inbox = self.config.inbox_dir
        if not inbox.exists():
            return []
        files = [
            f for f in inbox.iterdir()
            if f.is_file()
            and not f.name.startswith(".")
            and f.suffix.lower() in ALL_EXTENSIONS
            and ".chunk" not in f.name
            and not f.name.endswith(".meta")
        ]
        return sorted(files, key=lambda f: f.stat().st_mtime)

    def _recover_orphans(self) -> None:
        """恢复 processing/ 中的孤儿文件到 inbox/"""
        proc_dir = self.config.processing_dir
        if not proc_dir.exists():
            return
        for f in proc_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ALL_EXTENSIONS:
                log(f"  Recovering orphan: {f.name}")
                shutil.move(str(f), str(self.config.inbox_dir / f.name))


# ── 工具函数 ──────────────────────────────────────


def _lower_priority(level: str) -> None:
    """降低进程优先级"""
    try:
        if platform.system() == "Windows":
            import ctypes
            priority_map = {
                "below_normal": 0x4000,  # BELOW_NORMAL_PRIORITY_CLASS
                "low": 0x0040,           # IDLE_PRIORITY_CLASS
            }
            if level in priority_map:
                handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
                ctypes.windll.kernel32.SetPriorityClass(  # type: ignore[attr-defined]
                    handle, priority_map[level],
                )
        else:
            nice_map = {"below_normal": 10, "low": 19}
            if level in nice_map:
                os.nice(nice_map[level])
    except Exception:
        pass  # 优先级设置失败不影响主流程


def _wait_for_file_ready(
    path: Path, stable_seconds: int = 5,
) -> Path | None:
    """等待文件下载完成，返回就绪路径"""
    prev_size = -1
    stable_count = 0

    for _ in range(60):
        if not path.exists():
            # 文件消失，可能被改名
            candidates = [
                c for c in path.parent.glob(f"{path.stem}.*")
                if c.suffix.lower() in ALL_EXTENSIONS and c.is_file()
            ]
            if len(candidates) == 1:
                path = candidates[0]
                prev_size = -1
                stable_count = 0
                continue
            time.sleep(1)
            continue

        size = path.stat().st_size
        if size == prev_size and size > 0:
            stable_count += 1
            if stable_count >= stable_seconds:
                return path
        else:
            stable_count = 0
        prev_size = size
        time.sleep(1)

    return None


def _try_youtube_subtitles(url: str, language: str | None) -> str | None:
    """尝试用 youtube-transcript-api 抓字幕"""
    if not url:
        return None
    try:
        from inputs.youtube_subs import fetch_youtube_transcript
        return fetch_youtube_transcript(url, language)
    except Exception:
        return None


def _write_obsidian_note(
    config: Config,
    analysis: AnalysisResult,
    transcript: str,
    source_name: str,
    duration_sec: float,
    source_url: str = "",
    platform: str = "",
    is_ad: bool = False,
) -> Path:
    """写入 Obsidian Vault"""
    today = datetime.now().strftime("%Y-%m-%d")
    duration_min = int(duration_sec / 60)

    # 语义化标题 → 文件名安全版
    safe_title = ""
    if analysis.title:
        safe_title = "".join(
            c for c in analysis.title.replace(" ", "-").replace("/", "-")
            if c.isalnum() or c in "-_" or "\u4e00" <= c <= "\u9fff"
        ).lower()
    if not safe_title:
        safe_title = source_name.rsplit(".", 1)[0].replace(" ", "-").lower()

    scene = analysis.scene if analysis.scene in VALID_SCENES else "memo"
    type_tag = TYPE_TAGS.get(scene, scene)

    if platform:
        # 社交媒体: social-captures/
        ad_prefix = "ad-" if is_ad else ""
        note_name = f"{today}-{platform}-{ad_prefix}{safe_title}.md"
        output_dir = config.captures_output
        tags = ["social-capture", platform, type_tag]
        frontmatter = (
            f"---\n"
            f"date: {today}\n"
            f"platform: {platform}\n"
            f"type: {scene}\n"
            f"url: {source_url}\n"
            f"duration: {duration_min}min\n"
            f"tags: [{', '.join(tags)}]\n"
            f"---"
        )
    else:
        # 录音: recording-notes/
        note_name = f"{today}-{scene}-{safe_title}.md"
        output_dir = config.obsidian_output
        tags = ["recording-note", type_tag]
        url_line = f"\nurl: {source_url}" if source_url else ""
        frontmatter = (
            f"---\n"
            f"date: {today}\n"
            f"source: {source_name}{url_line}\n"
            f"duration: {duration_min}min\n"
            f"type: {scene}\n"
            f"tags: [{', '.join(tags)}]\n"
            f"---"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    note_path = output_dir / note_name

    # Layer 3 去重: 避免文件名冲突
    counter = 1
    while note_path.exists():
        stem = note_name.rsplit(".md", 1)[0]
        note_path = output_dir / f"{stem}-{counter}.md"
        counter += 1

    content = f"{frontmatter}\n\n{analysis.summary}\n\n---\n\n## 完整转录\n\n{transcript}"
    note_path.write_text(content, encoding="utf-8")
    log(f"  Obsidian note: {note_path.name} → {output_dir.name}/")
    return note_path
