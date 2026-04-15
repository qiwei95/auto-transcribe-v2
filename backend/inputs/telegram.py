#!/usr/bin/env python3
"""
Telegram 内容捕获机器人

接收链接 → 自动识别类型 → 音频下载到 inbox/ (走管道) / 文本保存到 Obsidian Captures

支持平台: YouTube, Bilibili, TikTok, 抖音, Instagram, Threads,
小红书, Twitter/X, Facebook, 以及任意网页。
"""

import asyncio
import ipaddress
import json
import re
import socket
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from logger import log

# ── 常量 ──────────────────────────────────────

# 短链域名（需要展开）
SHORT_LINK_DOMAINS = frozenset({
    "t.co", "bit.ly", "xhslink.com", "b23.tv",
    "vt.tiktok.com", "vm.tiktok.com", "tinyurl.com",
    "v.douyin.com", "fb.watch",
})

# 追踪参数黑名单
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "igshid", "ref", "s", "t", "si", "feature",
})

# URL 提取正则
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

# 私有 IP 范围
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
]

# 平台 referer 映射
PLATFORM_REFERERS: dict[str, str] = {
    "tiktok": "https://www.tiktok.com/",
    "douyin": "https://www.douyin.com/",
    "bilibili": "https://www.bilibili.com/",
    "instagram": "https://www.instagram.com/",
    "xiaohongshu": "https://www.xiaohongshu.com/",
    "twitter": "https://x.com/",
    "facebook": "https://www.facebook.com/",
}

# 广告 URL 参数检测
AD_PARAMS = frozenset({"ad_id", "campaign_id", "ad_name", "adset_id", "adset_name"})
AD_UTM_VALUES = frozenset({"cpc", "paid", "ppc", "cpm", "cpv"})

# 支持的语言前缀
LANG_CODES = frozenset({"en", "zh", "ja", "ko", "auto"})

# 每条消息最多处理的链接数
MAX_URLS_PER_MESSAGE = 5


# ── URL 工具函数 ──────────────────────────────────


def sanitize_filename(title: str) -> str:
    """清理文件名：保留中文和字母数字，最多 50 字符"""
    cleaned = re.sub(r'[^\w\u4e00-\u9fff\u3400-\u4dbf-]', ' ', title)
    cleaned = re.sub(r'\s+', '-', cleaned.strip())
    cleaned = cleaned.strip('-').lower()
    return cleaned[:50] if cleaned else "untitled"


async def resolve_url(url: str) -> str:
    """展开短链接，返回最终 URL"""
    parsed = urlparse(url)
    if parsed.hostname not in SHORT_LINK_DOMAINS:
        return url
    try:
        import httpx
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=10.0,
        ) as client:
            resp = await client.head(url)
            return str(resp.url)
    except Exception as e:
        log(f"[telegram] Short link resolve failed {url}: {e}")
        return url


def clean_url(url: str) -> str:
    """移除追踪参数"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=False)
    cleaned = {k: v for k, v in params.items() if k not in TRACKING_PARAMS}
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def classify_url(url: str) -> tuple[str, str]:
    """根据域名和路径判断 (平台, 内容类型)"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()

    if "youtube.com" in host or "youtu.be" in host:
        return ("youtube", "audio")
    if "bilibili.com" in host or "b23.tv" in host:
        return ("bilibili", "audio")
    if "tiktok.com" in host:
        return ("tiktok", "audio")
    if "douyin.com" in host:
        if "/note/" in path:
            return ("douyin", "text")
        return ("douyin", "audio")
    if "instagram.com" in host:
        if "/reel/" in path:
            return ("instagram", "audio")
        return ("instagram", "text")
    if "threads.net" in host or "threads.com" in host:
        return ("threads", "text")
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return ("xiaohongshu", "audio")
    if "twitter.com" in host or "x.com" in host:
        return ("twitter", "audio")
    if "facebook.com" in host or "fb.watch" in host or "fb.com" in host:
        if "/reel/" in path or "/watch" in path or "/videos/" in path:
            return ("facebook", "audio")
        return ("facebook", "text")
    return ("generic", "text")


def is_safe_url(url: str) -> tuple[bool, str]:
    """验证 URL 安全性：仅允许 http/https，阻止私有 IP"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return (False, f"Disallowed scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        return (False, "Invalid URL")

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return (False, f"Cannot resolve: {hostname}")

    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                return (False, f"Private IP blocked: {ip}")

    return (True, "")


def detect_ad_url(url: str) -> bool:
    """检测 URL 参数是否包含广告标识"""
    params = parse_qs(urlparse(url).query, keep_blank_values=False)
    if AD_PARAMS & set(params.keys()):
        return True
    utm_medium = params.get("utm_medium", [""])[0].lower()
    return utm_medium in AD_UTM_VALUES


def write_meta_sidecar(
    audio_path: Path, url: str, platform: str, language: str,
    chat_id: int = 0, is_ad: bool = False,
) -> None:
    """写 .meta JSON sidecar"""
    meta: dict = {"url": url, "platform": platform, "language": language}
    if chat_id:
        meta["chat_id"] = chat_id
    if is_ad:
        meta["is_ad"] = True
    Path(str(audio_path) + ".meta").write_text(json.dumps(meta))


# ── 音频下载 ──────────────────────────────────


async def download_douyin_direct(url: str, inbox: Path) -> Path | None:
    """用 iesdouyin 分享页提取视频 URL，再用 ffmpeg 转 mp3"""
    m = re.search(r'/video/(\d+)', url)
    if not m:
        log(f"[telegram] Douyin: can't extract video_id from {url}")
        return None

    video_id = m.group(1)
    share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"

    try:
        import httpx
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0,
        ) as client:
            resp = await client.get(share_url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
                    "Mobile/15E148 Safari/604.1"
                ),
                "Referer": "https://www.douyin.com/",
            })
            resp.raise_for_status()

        rm = re.search(
            r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*;?\s*</script>',
            resp.text, re.DOTALL,
        )
        if not rm:
            return None

        data = json.loads(rm.group(1))
        loader = data.get("loaderData", {})

        item = None
        for val in loader.values():
            if isinstance(val, dict) and "videoInfoRes" in val:
                items = val["videoInfoRes"].get("item_list", [])
                if items:
                    item = items[0]
                    break

        if not item:
            return None

        url_list = item.get("video", {}).get("play_addr", {}).get("url_list", [])
        if not url_list:
            return None

        play_url = url_list[0].replace("/playwm/", "/play/")
        desc = item.get("desc", "") or video_id
        safe_name = sanitize_filename(desc)
        output_path = inbox / f"{safe_name}.mp3"

        cmd = [
            "ffmpeg", "-y",
            "-headers", "Referer: https://www.douyin.com/\r\n",
            "-i", play_url,
            "-vn", "-acodec", "libmp3lame", "-q:a", "0",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode == 0 and output_path.exists():
            log(f"[telegram] Douyin direct download OK: {output_path.name}")
            return output_path

        log(f"[telegram] ffmpeg failed: {stderr.decode()[-300:]}")
        return None

    except Exception as e:
        log(f"[telegram] Douyin direct failed: {e}")
        return None


async def download_audio(
    url: str,
    inbox: Path,
    platform: str = "",
    language: str = "auto",
    chat_id: int = 0,
    is_ad: bool = False,
) -> Path | None:
    """用 yt-dlp 下载音频到 inbox/，返回文件路径。下载后写 .meta sidecar"""
    output_template = str(inbox / "%(title).50s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
        "--output", output_template, "--no-playlist",
        "--socket-timeout", "30", "--retries", "3",
    ]

    if platform == "douyin":
        cookie_file = Path(__file__).resolve().parent.parent / "cookies.txt"
        if cookie_file.exists():
            cmd.extend(["--cookies", str(cookie_file)])

    referer = PLATFORM_REFERERS.get(platform)
    if referer:
        cmd.extend(["--referer", referer])

    cmd.append(url)
    log(f"[telegram] Downloading audio: {url}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

        if proc.returncode != 0:
            log(f"[telegram] yt-dlp failed (code {proc.returncode})")
            if platform == "douyin":
                pw_path = await download_douyin_direct(url, inbox)
                if pw_path:
                    write_meta_sidecar(pw_path, url, platform, language, chat_id, is_ad)
                    return pw_path
            return None

        # 从 yt-dlp 输出找下载文件
        output_text = stdout.decode() + stderr.decode()
        for line in output_text.splitlines():
            if "Destination:" in line:
                path_str = line.split("Destination:", 1)[1].strip()
                p = Path(path_str)
                if p.exists():
                    log(f"[telegram] Audio downloaded: {p.name}")
                    write_meta_sidecar(p, url, platform, language, chat_id, is_ad)
                    return p

        # 备用：找最近修改的 mp3
        mp3_files = sorted(inbox.glob("*.mp3"), key=lambda f: f.stat().st_mtime)
        if mp3_files:
            latest = mp3_files[-1]
            if (datetime.now().timestamp() - latest.stat().st_mtime) < 60:
                log(f"[telegram] Audio downloaded (fallback): {latest.name}")
                write_meta_sidecar(latest, url, platform, language, chat_id, is_ad)
                return latest

        log("[telegram] yt-dlp completed but no output file found")
        return None

    except asyncio.TimeoutError:
        log(f"[telegram] yt-dlp timeout (600s): {url}")
        return None
    except Exception as e:
        log(f"[telegram] Download error: {e}")
        return None


# ── 文本抓取 ──────────────────────────────────


async def scrape_meta_tags(url: str) -> dict:
    """快速抓取 og 标签作为 fallback"""
    cmd = [
        "curl", "-sL", "-H",
        "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15",
        url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        page = stdout.decode("utf-8", errors="replace")

        from lxml import html as lxml_html
        tree = lxml_html.fromstring(page)
        og = {}
        for meta in tree.xpath("//meta[@property]"):
            prop = meta.get("property", "")
            if prop.startswith("og:"):
                og[prop] = meta.get("content", "")

        content = og.get("og:description", "")
        title = og.get("og:title", "")
        author = ""
        if " on " in title:
            author = title.split(" on ")[0].strip()
        elif title and not content:
            author = title

        return {"content": content, "title": title, "author": author}

    except Exception as e:
        log(f"[telegram] Meta tags scrape failed {url}: {e}")
        return {"content": "", "title": "", "author": ""}


async def scrape_threads_full(url: str) -> dict:
    """用 Playwright 抓取 Threads 完整内容"""
    log(f"[telegram] Playwright scraping Threads: {url}")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("[telegram] playwright not installed, fallback to meta tags")
        return await scrape_meta_tags(url)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            )
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            texts = await page.evaluate("""
                () => {
                    const blocks = [];
                    document.querySelectorAll('span').forEach(el => {
                        const t = el.textContent.trim();
                        if (t.length > 20 && !t.startsWith('Log in')
                            && !t.startsWith('Sign up') && !t.includes('© 2')
                            && !t.startsWith('Follow')) {
                            blocks.push(t);
                        }
                    });
                    const seen = new Set();
                    return blocks.filter(b => {
                        if (seen.has(b)) return false;
                        for (const existing of seen) {
                            if (existing.includes(b) || b.includes(existing)) {
                                seen.add(b);
                                return false;
                            }
                        }
                        seen.add(b);
                        return true;
                    });
                }
            """)

            author = await page.evaluate("""
                () => {
                    const el = document.querySelector('meta[property="og:title"]');
                    return el ? el.getAttribute('content') : '';
                }
            """)

            await browser.close()

            content = "\n\n".join(texts) if texts else ""
            author_name = ""
            if author and " on " in author:
                author_name = author.split(" on ")[0].strip()

            if content:
                log(f"[telegram] Playwright OK: {len(content)} chars, {len(texts)} blocks")
                return {"content": content, "title": author or "", "author": author_name}

            return await scrape_meta_tags(url)

    except Exception as e:
        log(f"[telegram] Playwright failed ({e}), fallback to meta tags")
        return await scrape_meta_tags(url)


async def scrape_defuddle(url: str) -> dict:
    """用 defuddle 抓取通用网页内容"""
    cmd = ["npx", "defuddle", "parse", url, "--markdown"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace").strip()

        if len(output) < 100:
            return {"content": "", "title": ""}

        lines = output.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else ""
        content = "\n".join(lines[1:]).strip() if len(lines) > 1 else output

        return {"content": content, "title": title}

    except Exception as e:
        log(f"[telegram] defuddle scrape failed {url}: {e}")
        return {"content": "", "title": ""}


async def scrape_instagram_embed(url: str) -> dict:
    """用 Instagram Embed 端点抓取帖子文字"""
    parsed = urlparse(url)
    match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', parsed.path)
    if not match:
        return await scrape_meta_tags(url)

    post_id = match.group(1)
    embed_url = f"https://www.instagram.com/p/{post_id}/embed/captioned/"

    try:
        import httpx
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            },
        ) as client:
            resp = await client.get(embed_url)
            resp.raise_for_status()

        from lxml import html as lxml_html
        tree = lxml_html.fromstring(resp.text)

        caption_el = tree.xpath('//*[contains(@class,"Caption")]//text()')
        content = " ".join(t.strip() for t in caption_el if t.strip())

        author_el = tree.xpath('//*[contains(@class,"UsernameText")]//text()')
        author = author_el[0].strip() if author_el else ""

        if content:
            log(f"[telegram] Instagram embed OK: {len(content)} chars, author={author}")
            return {"content": content, "title": f"{author} on Instagram", "author": author}

        return await scrape_meta_tags(url)

    except Exception as e:
        log(f"[telegram] Instagram embed failed ({e}), fallback")
        return await scrape_meta_tags(url)


async def scrape_text(url: str, platform: str) -> dict:
    """文本抓取路由"""
    if platform == "threads":
        result = await scrape_threads_full(url)
    elif platform == "instagram":
        result = await scrape_instagram_embed(url)
    else:
        result = await scrape_defuddle(url)

    if not result.get("content"):
        return {"content": "", "error": "Scrape failed"}
    return result


# ── Obsidian 写入（文本类内容直接写，不走管道） ──


def write_capture(
    content: str, metadata: dict, captures_output: Path,
) -> Path:
    """写入 social-captures/ 笔记"""
    today = datetime.now().strftime("%Y-%m-%d")
    title = metadata.get("title", "untitled")
    safe_title = sanitize_filename(title)
    platform = metadata.get("platform", "unknown")
    url = metadata.get("url", "")
    author = metadata.get("author", "")

    base_name = f"{today}-{platform}-{safe_title}"
    file_path = captures_output / f"{base_name}.md"
    counter = 1
    while file_path.exists():
        file_path = captures_output / f"{base_name}-{counter}.md"
        counter += 1

    tags = ["social-capture", platform, "text"]
    frontmatter = (
        f"---\n"
        f"date: {today}\n"
        f"platform: {platform}\n"
        f"type: text\n"
        f"url: {url}\n"
    )
    if author:
        frontmatter += f"author: {author}\n"
    frontmatter += (
        f"tags: [{', '.join(tags)}]\n"
        f"---"
    )

    display_title = title if title else safe_title
    note = f"{frontmatter}\n\n# {display_title}\n\n{content}\n"

    captures_output.mkdir(parents=True, exist_ok=True)
    file_path.write_text(note, encoding="utf-8")
    log(f"[telegram] Saved capture: {file_path.name}")
    return file_path


# ── 核心处理逻辑 ──────────────────────────────


async def process_single_url(
    url: str,
    inbox: Path,
    captures_output: Path,
    language: str = "auto",
    chat_id: int = 0,
    is_ad: bool = False,
) -> str:
    """处理单个 URL，返回回复文本"""
    # 1. 展开短链
    resolved = await resolve_url(url)

    # 2. 广告检测（清理参数之前）
    if not is_ad:
        is_ad = detect_ad_url(resolved)

    # 3. 清理追踪参数
    cleaned = clean_url(resolved)

    # 4. 安全检查
    safe, reason = is_safe_url(cleaned)
    if not safe:
        return f"✗ URL not safe: {reason}\n{url}"

    # 5. 分类
    platform, content_type = classify_url(cleaned)
    ad_label = " [ad]" if is_ad else ""
    log(f"[telegram] Processing: {cleaned} → {platform}/{content_type}{ad_label}")

    # 6. 按类型处理
    if content_type == "audio":
        audio_path = await download_audio(
            cleaned, inbox, platform,
            language=language, chat_id=chat_id, is_ad=is_ad,
        )
        if audio_path:
            return (
                f"✓ Audio queued for transcription\n"
                f"Source: {platform.capitalize()}\n"
                f"⏳ Will appear in Obsidian when done"
            )
        log(f"[telegram] Audio download failed, falling back to text: {cleaned}")
        content_type = "text"

    # 文本抓取
    result = await scrape_text(cleaned, platform)
    if result.get("error"):
        return f"✗ Scrape failed: {result['error']}\n{cleaned}"

    content = result["content"]
    title = result.get("title", "")
    author = result.get("author", "")

    metadata = {
        "title": title,
        "platform": platform,
        "url": cleaned,
        "author": author,
    }
    write_capture(content, metadata, captures_output)

    preview = content[:500]
    if len(content) > 500:
        preview += "..."

    source_line = platform.capitalize()
    if author:
        source_line += f" / {author}"

    return (
        f"✓ Saved to Obsidian Captures\n"
        f"Source: {source_line}\n"
        f"---\n"
        f"{preview}"
    )


# ── Telegram Bot ─────────────────────────────


class TelegramBot:
    """Telegram 内容捕获机器人"""

    def __init__(
        self,
        token: str,
        inbox: Path,
        captures_output: Path,
        allowed_users: list[int] | None = None,
    ):
        self.token = token
        self.inbox = inbox
        self.captures_output = captures_output
        self.allowed_users = allowed_users or []
        self._thread: threading.Thread | None = None
        self._app = None

    def start(self) -> None:
        """启动 bot（后台线程）"""
        if not self.token:
            log("[telegram] No bot token configured, skipping")
            return

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="telegram-bot",
        )
        self._thread.start()
        log(f"[telegram] Bot started (allowed users: {len(self.allowed_users) or 'all'})")

    def stop(self) -> None:
        """停止 bot"""
        if self._app:
            # 请求 Application 停止
            self._app.stop_running()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
            log("[telegram] Bot stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        """在新线程中运行 bot 的事件循环"""
        from telegram import Update
        from telegram.ext import (
            Application,
            CommandHandler,
            MessageHandler,
            filters,
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        app = Application.builder().token(self.token).build()
        self._app = app

        app.add_handler(CommandHandler("start", self._handle_start))
        app.add_handler(CommandHandler("help", self._handle_help))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message),
        )

        app.run_polling(allowed_updates=Update.ALL_TYPES)

    async def _handle_start(self, update, context) -> None:
        await update.message.reply_text(
            "你好！我是内容捕获机器人。\n\n"
            "发送链接给我，我会自动处理：\n"
            "- 视频/音频链接 → 下载并加入转录队列\n"
            "- 文章/帖子链接 → 保存到 Obsidian\n\n"
            "支持平台：YouTube, Bilibili, TikTok, Instagram, "
            "Threads, 小红书, Twitter/X, 以及任意网页"
        )

    async def _handle_help(self, update, context) -> None:
        await update.message.reply_text(
            "使用方法：直接发送一个或多个链接\n\n"
            "音频类（自动下载转录）：\n"
            "  YouTube / Bilibili / TikTok\n"
            "  Instagram Reels / 小红书 / Twitter\n\n"
            "文本类（保存到 Obsidian）：\n"
            "  Threads / Instagram 帖子\n"
            "  任意网页文章\n\n"
            "语言指定（可选，加在链接前面）：\n"
            "  en https://... → 英文转录\n"
            "  zh https://... → 中文转录\n"
            "  不加前缀 → 自动检测语言\n\n"
            f"每条消息最多处理 {MAX_URLS_PER_MESSAGE} 个链接。"
        )

    async def _handle_message(self, update, context) -> None:
        user = update.effective_user
        if not user:
            return

        if self.allowed_users and user.id not in self.allowed_users:
            log(f"[telegram] Unauthorized user: {user.id} ({user.username})")
            await update.message.reply_text("你没有使用权限。")
            return

        text = update.message.text or ""

        # 解析前缀：ad / 语言码
        language = "auto"
        is_ad = False
        words = text.strip().split()
        consumed = 0
        for word in words:
            w = word.lower()
            if w == "ad" and not is_ad:
                is_ad = True
                consumed += len(word) + 1
            elif w in LANG_CODES and language == "auto":
                language = w
                consumed += len(word) + 1
            else:
                break
        text = text.strip()[consumed:]

        urls = URL_PATTERN.findall(text)
        if not urls:
            await update.message.reply_text(
                "请发送链接\n\n"
                "💡 可加语言前缀指定转录语言：\n"
                "en https://... → 英文\n"
                "zh https://... → 中文\n"
                "不加前缀 → 自动检测"
            )
            return

        if len(urls) > MAX_URLS_PER_MESSAGE:
            await update.message.reply_text(
                f"每条消息最多处理 {MAX_URLS_PER_MESSAGE} 个链接，已截取前 {MAX_URLS_PER_MESSAGE} 个。"
            )
            urls = urls[:MAX_URLS_PER_MESSAGE]

        log(f"[telegram] {len(urls)} URL(s) from {user.username or user.id}")

        for url in urls:
            url = url.rstrip(",.;:!?)>」】）》")

            status_msg = await update.message.reply_text(f"⏳ 处理中...\n{url}")
            try:
                reply = await process_single_url(
                    url, self.inbox, self.captures_output,
                    language=language,
                    chat_id=update.effective_chat.id,
                    is_ad=is_ad,
                )
            except Exception as e:
                log(f"[telegram] Error processing {url}: {e}")
                reply = f"✗ Error: {e}\n{url}"
            try:
                await status_msg.edit_text(reply)
            except Exception:
                await update.message.reply_text(reply)
