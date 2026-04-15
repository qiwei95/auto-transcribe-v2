#!/usr/bin/env python3
"""
Plaud 录音云端拉取

通过 Plaud 网页 API 下载录音到 inbox/。
认证: Bearer token 存放在 ~/.plaud/config.json（从 web.plaud.ai localStorage 获取）。
"""

import base64
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from logger import log

# 允许的 Plaud API 域名（防止 config 被篡改后 token 发到别处）
ALLOWED_API_BASES = frozenset({
    "https://api-apse1.plaud.ai",
    "https://api.plaud.ai",
    "https://api-euc1.plaud.ai",
})

# 允许的下载 URL 域名后缀（S3 预签名 URL）
ALLOWED_DOWNLOAD_HOSTS = (".amazonaws.com", ".plaud.ai")

# 模拟网页端请求头
_WEB_HEADERS = {
    "Origin": "https://web.plaud.ai",
    "Referer": "https://web.plaud.ai/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36"
    ),
}

# Plaud 自带示例录音关键词
_DEMO_KEYWORDS = frozenset({"welcome_to_plaud", "how_to_use_plaud", "steve_jobs"})

PLAUD_CONFIG_PATH = Path.home() / ".plaud" / "config.json"


def is_safe_download_url(url: str) -> bool:
    """检查下载 URL 是否在允许的域名范围内"""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    return any(parsed.netloc.endswith(h) for h in ALLOWED_DOWNLOAD_HOSTS)


def load_plaud_config(config_path: Path = PLAUD_CONFIG_PATH) -> dict:
    """读取 ~/.plaud/config.json"""
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text())


def _api_get(url: str, token: str) -> dict | bytes:
    """发送 GET 请求到 Plaud API"""
    req = Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in _WEB_HEADERS.items():
        req.add_header(k, v)

    with urlopen(req, timeout=60) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
        if "json" in content_type:
            return json.loads(data)
        return data


def check_token_expiry(token: str) -> int | None:
    """检查 token 剩余天数，返回天数或 None"""
    try:
        payload = token.split(".")[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        data = json.loads(base64.b64decode(payload))
        exp = data.get("exp", 0)
        days_left = (exp - time.time()) / 86400
        return int(days_left)
    except Exception:
        return None


def fetch_recordings(api_base: str, token: str) -> list[dict]:
    """获取所有录音列表（过滤掉示例和回收站）"""
    resp = _api_get(f"{api_base}/file/simple/web", token)

    if not isinstance(resp, dict) or resp.get("status") != 0:
        log(f"  [plaud] API error: {resp}")
        return []

    result = []
    for item in resp.get("data_file_list", []):
        if item.get("is_trash", False):
            continue
        name = (item.get("filename", "") or "").lower().replace(" ", "_")
        if any(kw in name for kw in _DEMO_KEYWORDS):
            continue
        result.append(item)
    return result


def download_mp3(api_base: str, token: str, file_id: str) -> bytes | None:
    """通过临时 URL 下载 MP3"""
    try:
        resp = _api_get(f"{api_base}/file/temp-url/{file_id}", token)
        if isinstance(resp, dict) and resp.get("status") == 0:
            mp3_url = resp.get("temp_url", "")
            if mp3_url:
                if not is_safe_download_url(mp3_url):
                    log(f"  [plaud] Unsafe download URL: {mp3_url[:80]}")
                    return None
                req = Request(mp3_url)
                with urlopen(req, timeout=120) as dl_resp:
                    return dl_resp.read()
    except (HTTPError, URLError) as e:
        log(f"  [plaud] MP3 download failed: {e}")
    return None


def download_raw(api_base: str, token: str, file_id: str) -> bytes | None:
    """直接下载原始格式"""
    try:
        data = _api_get(f"{api_base}/file/download/{file_id}", token)
        if isinstance(data, bytes) and len(data) > 0:
            return data
    except (HTTPError, URLError) as e:
        log(f"  [plaud] Raw download failed: {e}")
    return None


def make_filename(recording: dict) -> str:
    """从录音信息生成文件名"""
    name = recording.get("filename", "")

    if name:
        safe = name.replace(" ", "_").replace(":", "-")
        safe = re.sub(r"[^a-zA-Z0-9\-_\u4e00-\u9fff]", "_", safe)
        safe = safe.strip("._")
        if safe:
            return safe[:100]

    start = recording.get("start_time", 0)
    if start:
        ts = start / 1000 if start > 1e12 else start
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d_%H-%M-%S")

    return f"plaud_{int(time.time())}"


def load_pulled_db(db_path: Path) -> dict:
    """已拉取录音的记录，JSON 损坏时备份后重置"""
    if db_path.exists():
        try:
            return json.loads(db_path.read_text())
        except (json.JSONDecodeError, ValueError):
            log("[plaud] pulled.json corrupted, resetting")
            import shutil
            shutil.copy2(db_path, db_path.with_suffix(".json.bak"))
            return {}
    return {}


def save_pulled_db(db: dict, db_path: Path) -> None:
    """原子写入：先写临时文件再 rename"""
    fd, tmp = tempfile.mkstemp(dir=db_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, db_path)
    except BaseException:
        os.unlink(tmp)
        raise


def pull_once(
    api_base: str,
    token: str,
    local_inbox: Path,
    pulled_db_path: Path,
) -> int:
    """拉取一次新录音，返回下载数"""
    local_inbox.mkdir(parents=True, exist_ok=True)

    recordings = fetch_recordings(api_base, token)
    if not recordings:
        return 0

    pulled = load_pulled_db(pulled_db_path)
    new_count = 0

    for rec in recordings:
        file_id = rec.get("id", "")
        if not file_id or file_id in pulled:
            continue

        filename = make_filename(rec)
        duration_ms = rec.get("duration", 0)
        duration_sec = duration_ms // 1000
        log(f"  [plaud] Downloading: {filename} ({duration_sec // 60}m{duration_sec % 60}s)")

        # 优先 MP3，回退原始格式
        audio_data = download_mp3(api_base, token, file_id)
        ext = "mp3"
        if not audio_data:
            audio_data = download_raw(api_base, token, file_id)
            ext = "ogg"

        if not audio_data:
            log(f"  [plaud] Download failed: {filename}")
            continue

        dest = local_inbox / f"{filename}.{ext}"
        counter = 1
        while dest.exists():
            dest = local_inbox / f"{filename}_{counter}.{ext}"
            counter += 1

        dest.write_bytes(audio_data)

        # 写 .meta sidecar
        meta = {"platform": "", "language": "", "source": "plaud"}
        meta_path = Path(str(dest) + ".meta")
        meta_path.write_text(json.dumps(meta))

        pulled[file_id] = {
            "filename": dest.name,
            "downloaded_at": datetime.now().isoformat(),
            "title": rec.get("filename", ""),
            "duration": duration_sec,
        }
        save_pulled_db(pulled, pulled_db_path)
        new_count += 1

        log(f"  [plaud] Saved: {dest.name} ({len(audio_data) / 1024:.0f} KB)")

    return new_count


class PlaudSync:
    """Plaud 录音云端拉取后台任务"""

    def __init__(
        self,
        local_inbox: Path,
        base_dir: Path,
        interval_sec: int = 300,
        config_path: Path = PLAUD_CONFIG_PATH,
    ):
        self.local_inbox = local_inbox
        self.pulled_db_path = base_dir / "plaud-pulled.json"
        self.interval_sec = interval_sec
        self.config_path = config_path
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台拉取线程"""
        plaud_cfg = load_plaud_config(self.config_path)
        token = plaud_cfg.get("token", "")
        api_base = plaud_cfg.get("api_base", "https://api-apse1.plaud.ai")

        if not token:
            log(f"[plaud] No token found in {self.config_path}")
            log("[plaud] Skipping — configure token to enable")
            return

        if api_base not in ALLOWED_API_BASES:
            log(f"[plaud] Untrusted api_base: {api_base}")
            return

        # 去掉 "bearer " 前缀
        if token.lower().startswith("bearer "):
            token = token[7:]

        days_left = check_token_expiry(token)
        if days_left is not None:
            if days_left < 30:
                log(f"[plaud] WARNING: Token expires in {days_left} days!")
                log("  Update: web.plaud.ai → F12 → Console → localStorage.getItem('tokenstr')")
            elif days_left < 60:
                log(f"[plaud] Token valid for {days_left} days")

        self._api_base = api_base
        self._token = token
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="plaud-sync",
        )
        self._thread.start()
        log(f"[plaud] Started (every {self.interval_sec}s)")

    def stop(self) -> None:
        """停止后台拉取"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
            log("[plaud] Stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                n = pull_once(
                    self._api_base,
                    self._token,
                    self.local_inbox,
                    self.pulled_db_path,
                )
                if n > 0:
                    log(f"[plaud] Pulled {n} recording(s)")
            except Exception as e:
                log(f"[plaud] Error: {e}")

            self._stop_event.wait(self.interval_sec)
