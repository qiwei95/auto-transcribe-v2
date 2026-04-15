#!/usr/bin/env python3
"""
Claude CLI 总结引擎

功能:
- 一次调用完成 分类 + 标题 + 结构化总结
- 按场景选择不同 prompt 模板
- 社交媒体视频自动路由 (短视频/长视频/广告)
- 重试 + 超时控制
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from logger import log


VALID_SCENES = (
    "meeting", "content", "memo", "1on1", "class", "call",
    "daylog", "discussion", "video", "video-short", "video-long", "ad",
)

TYPE_TAGS = {
    "meeting": "会议", "content": "内容", "memo": "备忘",
    "1on1": "一对一", "class": "课堂", "call": "通话",
    "daylog": "日志", "discussion": "研讨", "video": "视频",
    "video-short": "短视频", "video-long": "长视频", "ad": "广告",
}

# 社交媒体视频 prompt 路由阈值
SHORT_VIDEO_THRESHOLD = 300  # 5 分钟


@dataclass(frozen=True)
class AnalysisResult:
    """Claude 分析结果"""
    scene: str        # meeting / memo / video-short / ...
    title: str        # AI 生成的标题
    summary: str      # 结构化总结正文


# 兜底 prompt（prompts/ 目录没有对应模板时使用）
_DEFAULT_PROMPT = """请将以下录音转录整理成结构化笔记。

要求：
1. 用中文输出
2. 提取核心要点
3. 列出行动项（如果有）
4. 保持简洁，去掉口语化表达
"""


class Summarizer:
    """Claude CLI 总结引擎"""

    def __init__(
        self,
        prompts_dir: Path,
        timeout: int = 1800,
        max_retries: int = 3,
        max_chars: int = 80000,
    ):
        self.prompts_dir = prompts_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_chars = max_chars

    def analyze(
        self,
        transcript: str,
        scene: str | None = None,
        platform: str = "",
        duration_sec: float = 0,
        is_ad: bool = False,
    ) -> AnalysisResult:
        """一次 Claude 调用完成分类+标题+总结

        Args:
            transcript: 转录文本
            scene: 预设场景 (None=让 Claude 分类)
            platform: 社交媒体平台名 (空=录音)
            duration_sec: 音频时长
            is_ad: 是否为广告内容
        """
        # 长度保护
        if len(transcript) > self.max_chars:
            log(f"  Transcript too long ({len(transcript)} chars), truncating to {self.max_chars}")
            transcript = (
                transcript[:self.max_chars]
                + "\n\n[... transcript truncated ...]"
            )

        # 选择 prompt 模板
        if platform:
            scene = select_prompt(platform, duration_sec, is_ad)
        need_classify = scene is None

        # 加载 prompt 文件
        scene_prompt = self._load_prompt(scene or "memo")

        # 构建合并 prompt
        parts = []
        if need_classify:
            valid = ", ".join(VALID_SCENES)
            parts.append(
                f"首先，判断这段录音的类型，从以下选项中选一个：{valid}\n"
                "在第一行输出：===SCENE=== 类型名\n\n"
            )
        parts.append("然后，生成一个简洁的中文标题（最多 30 字）。\n")
        parts.append("在单独一行输出：===TITLE=== 标题内容\n\n")
        parts.append("最后，按以下要求整理内容：\n\n")
        parts.append(scene_prompt)
        parts.append(f"\n\n## 转录内容\n\n{transcript}")

        full_prompt = "".join(parts)
        input_chars = len(full_prompt)
        log(f"  Claude analyzing (scene: {scene or 'auto'}, input: {input_chars} chars)...")

        # 调用 Claude CLI
        output = self._call_claude(full_prompt)
        if not output:
            return AnalysisResult(scene=scene or "memo", title="", summary="")

        # 估算 token 消耗
        est_input = input_chars // 2
        est_output = len(output) // 2
        log(f"  Token estimate: ~{est_input} input + ~{est_output} output = ~{est_input + est_output} total")

        return _parse_output(output, scene or "memo", need_classify)

    def _load_prompt(self, scene: str) -> str:
        """加载 prompt 模板文件"""
        prompt_file = self.prompts_dir / f"{scene}.md"
        if prompt_file.exists():
            return prompt_file.read_text()

        # 回退到 memo
        fallback = self.prompts_dir / "memo.md"
        if fallback.exists():
            return fallback.read_text()

        return _DEFAULT_PROMPT

    def _call_claude(self, prompt: str) -> str:
        """调用 Claude CLI，带重试和超时"""
        for attempt in range(1, self.max_retries + 1):
            try:
                result = subprocess.run(
                    ["claude", "-p", "--model", "sonnet", "-"],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                log(f"  Claude returned empty (attempt {attempt})")
            except subprocess.TimeoutExpired:
                log(f"  Claude timeout (attempt {attempt})")
            except Exception as e:
                log(f"  Claude error: {e} (attempt {attempt})")

            if attempt < self.max_retries:
                time.sleep(5)

        return ""


def select_prompt(
    platform: str, duration_sec: float, is_ad: bool,
) -> str:
    """社交媒体视频 → 选 prompt 模板名"""
    if is_ad:
        return "ad"
    if duration_sec < SHORT_VIDEO_THRESHOLD:
        return "video-short"
    return "video-long"


def _parse_output(
    output: str, default_scene: str, need_classify: bool,
) -> AnalysisResult:
    """从 Claude 合并输出中解析 scene, title, summary"""
    scene = default_scene
    title = ""
    summary_lines = []

    for line in output.splitlines():
        if line.startswith("===SCENE==="):
            raw = line.split("===SCENE===", 1)[1].strip().lower()
            # 长名称优先匹配 (video-short 在 video 之前)
            for s in sorted(VALID_SCENES, key=len, reverse=True):
                if s in raw:
                    scene = s
                    break
            continue
        if line.startswith("===TITLE==="):
            title = line.split("===TITLE===", 1)[1].strip()
            # 清洗标题
            for ch in '"\'「」《》:：':
                title = title.replace(ch, "")
            title = title.strip()[:50]
            continue
        # 跳过模板分隔符
        if line.startswith(("===META===", "===SUMMARY===",
                           "content_type:", "intent:")):
            continue
        summary_lines.append(line)

    summary = "\n".join(summary_lines).strip()
    if title:
        log(f"  Title: {title}")
    log(f"  Scene: {scene}, summary: {len(summary)} chars")

    return AnalysisResult(scene=scene, title=title, summary=summary)
