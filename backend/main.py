#!/usr/bin/env python3
"""
Auto-Transcribe v2 — FastAPI 后端入口

使用方式:
  auto-transcribe serve          # 启动 API 服务 (Tauri sidecar 调用)
  auto-transcribe run file.m4a   # 直接处理文件 (CLI 模式)
  auto-transcribe status         # 查看当前状态
"""

import argparse
import asyncio
import json
import shutil
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import load_config
from inputs.icloud import ICloudSync
from inputs.plaud import PlaudSync
from inputs.telegram import TelegramBot
from logger import log
from pipeline import Pipeline
from watcher import InboxWatcher

# ── 全局状态 ──

_config = load_config()
_pipeline = Pipeline(_config)
_watcher: InboxWatcher | None = None
_icloud: ICloudSync | None = None
_plaud: PlaudSync | None = None
_telegram: TelegramBot | None = None
_ws_clients: list[WebSocket] = []
_ws_lock = threading.Lock()


# ── WebSocket 广播 ──

def _broadcast(step: str, filename: str, extra: dict) -> None:
    """向所有 WebSocket 客户端广播进度"""
    message = json.dumps({
        "type": "progress",
        "step": step,
        "filename": filename,
        **{k: v for k, v in extra.items() if v is not None},
    })
    with _ws_lock:
        clients = _ws_clients[:]
    for ws in clients:
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_text(message),
                _loop,
            )
        except Exception:
            with _ws_lock:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)


_pipeline.on_progress = _broadcast
_loop: asyncio.AbstractEventLoop


# ── FastAPI 应用 ──

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global _watcher, _icloud, _plaud, _telegram, _loop
    _loop = asyncio.get_event_loop()

    # 启动文件监控
    _watcher = InboxWatcher(
        _config.inbox_dir,
        lambda: _pipeline.process_inbox(),
    )
    _watcher.start()

    # 启动可选输入源
    if _config.icloud_enabled:
        _icloud = ICloudSync(
            icloud_inbox=_config.icloud_inbox,
            local_inbox=_config.inbox_dir,
            stable_seconds=_config.file_stable_seconds,
        )
        _icloud.start()

    if _config.plaud_enabled:
        _plaud = PlaudSync(
            local_inbox=_config.inbox_dir,
            base_dir=_config.base_dir,
        )
        _plaud.start()

    if _config.telegram_bot_token:
        _telegram = TelegramBot(
            token=_config.telegram_bot_token,
            inbox=_config.inbox_dir,
            captures_output=_config.captures_output,
            allowed_users=_config.telegram_allowed_users,
        )
        _telegram.start()

    log(f"Auto-Transcribe v2 started on http://127.0.0.1:8765")
    log(f"  Base dir: {_config.base_dir}")
    log(f"  Whisper: {_config.whisper_model} ({_config.whisper_device})")
    log(f"  Obsidian: {_config.obsidian_output}")

    yield

    # 关闭
    if _telegram:
        _telegram.stop()
    if _plaud:
        _plaud.stop()
    if _icloud:
        _icloud.stop()
    if _watcher:
        _watcher.stop()
    _pipeline.db.close()


app = FastAPI(title="Auto-Transcribe", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri 本地访问
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST API ──

@app.get("/api/status")
async def get_status():
    """当前处理状态"""
    current = _pipeline.db.get_current_job()
    today = _pipeline.db.get_today_done()
    inbox_count = len(list(_config.inbox_dir.glob("*"))) if _config.inbox_dir.exists() else 0
    return {
        "paused": _pipeline.paused,
        "current_job": current,
        "today_count": len(today),
        "inbox_count": inbox_count,
        "config": {
            "whisper_model": _config.whisper_model,
            "whisper_device": _config.whisper_device,
            "obsidian_output": str(_config.obsidian_output),
        },
    }


@app.get("/api/history")
async def get_history(
    limit: int = 50, offset: int = 0,
    type: str = "", q: str = "",
):
    """处理历史"""
    items = _pipeline.db.get_history(
        limit=limit, offset=offset,
        type_filter=type, search=q,
    )
    return {"items": items, "limit": limit, "offset": offset}


@app.get("/api/today")
async def get_today():
    """今日完成"""
    return {"items": _pipeline.db.get_today_done()}


@app.post("/api/upload")
async def upload_file(file: UploadFile):
    """上传文件到 inbox/"""
    _config.inbox_dir.mkdir(parents=True, exist_ok=True)
    # 安全：只取文件名，防止路径穿越
    safe_name = Path(file.filename or "upload.tmp").name
    if not safe_name or safe_name.startswith("."):
        safe_name = "upload.tmp"
    dest = _config.inbox_dir / safe_name

    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    log(f"Uploaded: {dest.name}")

    # 后台处理
    threading.Thread(
        target=_pipeline.process_inbox,
        daemon=True,
    ).start()

    return {"filename": dest.name, "status": "queued"}


@app.post("/api/pause")
async def toggle_pause():
    """暂停/恢复处理"""
    _pipeline.paused = not _pipeline.paused
    status = "paused" if _pipeline.paused else "resumed"
    log(f"Processing {status}")
    return {"paused": _pipeline.paused}


@app.get("/api/config")
async def get_config():
    """读取当前配置"""
    return {
        "base_dir": str(_config.base_dir),
        "obsidian_output": str(_config.obsidian_output),
        "captures_output": str(_config.captures_output),
        "whisper_model": _config.whisper_model,
        "whisper_language": _config.whisper_language,
        "whisper_device": _config.whisper_device,
        "process_priority": _config.process_priority,
        "plaud_enabled": _config.plaud_enabled,
        "icloud_enabled": _config.icloud_enabled,
        "telegram_configured": bool(_config.telegram_bot_token),
    }


@app.put("/api/config")
async def update_config(body: dict):
    """更新配置（运行时修改，不持久化到 yaml）"""
    updatable = {
        "whisper_model", "whisper_language", "whisper_device",
        "process_priority", "plaud_enabled", "icloud_enabled",
        "obsidian_output", "captures_output",
    }
    changed = {}
    for key, value in body.items():
        if key in updatable:
            if key in ("obsidian_output", "captures_output"):
                setattr(_config, key, Path(value).expanduser())
            else:
                setattr(_config, key, value)
            changed[key] = value
    return {"updated": changed}


@app.get("/api/inputs")
async def get_inputs_status():
    """输入源状态"""
    return {
        "icloud": {
            "enabled": _config.icloud_enabled,
            "running": _icloud.running if _icloud else False,
            "inbox": str(_config.icloud_inbox),
        },
        "plaud": {
            "enabled": _config.plaud_enabled,
            "running": _plaud.running if _plaud else False,
        },
        "telegram": {
            "enabled": bool(_config.telegram_bot_token),
            "running": _telegram.running if _telegram else False,
        },
    }


@app.get("/api/system")
async def get_system_info():
    """系统信息"""
    import platform as plat
    gpu_info = "Unknown"
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = torch.cuda.get_device_name(0)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            gpu_info = "Apple Silicon (MPS)"
        else:
            gpu_info = "CPU only"
    except ImportError:
        gpu_info = "CPU only (torch not installed)"

    return {
        "platform": plat.system(),
        "machine": plat.machine(),
        "python": plat.python_version(),
        "gpu": gpu_info,
        "node": plat.node(),
    }


# ── WebSocket ──

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """实时进度推送"""
    await ws.accept()
    with _ws_lock:
        _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        with _ws_lock:
            if ws in _ws_clients:
                _ws_clients.remove(ws)


# ── CLI 入口 ──

def cli() -> None:
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="Auto-Transcribe: local AI transcription → Obsidian notes",
    )
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_cmd = sub.add_parser("serve", help="Start API server")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.add_argument("--host", default="127.0.0.1")

    # run
    run_cmd = sub.add_parser("run", help="Process files directly")
    run_cmd.add_argument("files", nargs="+", help="Audio/video files to process")

    # status
    sub.add_parser("status", help="Show current status")

    args = parser.parse_args()

    if args.command == "serve" or args.command is None:
        port = getattr(args, "port", 8765)
        host = getattr(args, "host", "127.0.0.1")
        uvicorn.run(app, host=host, port=port, log_level="warning")

    elif args.command == "run":
        config = load_config()
        pipeline = Pipeline(config)
        for f in args.files:
            path = Path(f)
            if not path.exists():
                log(f"File not found: {f}")
                continue
            # 复制到 inbox 再处理（保持流程一致）
            config.inbox_dir.mkdir(parents=True, exist_ok=True)
            dest = config.inbox_dir / path.name
            shutil.copy2(str(path), str(dest))
            result = pipeline.process_file(dest)
            if result:
                log(f"✓ {result.title} → {result.note_path}")
            else:
                log(f"✗ Failed to process: {f}")

    elif args.command == "status":
        config = load_config()
        from dedup import DedupDB
        db = DedupDB(config.db_path)
        current = db.get_current_job()
        today = db.get_today_done()
        print(f"Status: {'Processing' if current else 'Idle'}")
        if current:
            progress = db.step_progress(current["step"])
            print(f"  Current: {current['filename']} ({progress})")
        print(f"  Today: {len(today)} completed")
        db.close()


if __name__ == "__main__":
    cli()
