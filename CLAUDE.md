# Auto-Transcribe v2 — 协作规则

## 项目定位

本地音频/视频自动转录管道，输出到 Obsidian。
- **架构**：backend (Python, FastAPI/CLI) + frontend (Tauri 桌面 app)
- **隐私优先**：转录全程本地（faster-whisper），只有摘要才用 Claude CLI
- **多输入源**：拖放、Telegram bot、Plaud 录音器、iCloud Voice Memos

## ⚠️ 与 v1 的关系（重要）

代码独立重写，**但数据目录仍复用 v1 路径**：
- `~/Documents/Claude-Output/auto-transcribe/inbox/` — 入站文件
- `~/Documents/Claude-Output/auto-transcribe/done/` — 处理完成的原始音频
- `~/Documents/Claude-Output/auto-transcribe/auto-transcribe.db` — SQLite 状态

→ **不要动 v1 目录**。`backend/config.yaml` 里 `base_dir` 就是指 v1 路径。
→ v1 的 launchd 已 unload 移到 `~/Library/LaunchAgents/_archived-auto-transcribe-v1/`。
→ 从 v1 迁移用 `backend/migrate-from-v1.py`（已跑过）。

## 入口脚本

| 用途 | 命令 |
|------|------|
| 启动后端服务（含 WebSocket） | `cd backend && python main.py serve` |
| CLI 单次跑（无 GUI） | `cd backend && python main.py run <file>` |
| 启动桌面 app（dev） | `cd frontend && npm run tauri dev` |
| 重新摘要某个已转录文件 | `python backend/re-summarize.py` |
| 重新处理（重新跑全流程） | `python backend/reprocess.py` |

## 关键模块（backend/）

- `pipeline.py` — 主流水线编排
- `dedup.py` — SHA256 去重（防止重复处理）
- `summarizer.py` — Claude CLI 调用，16 个场景模板（meeting/lecture/video/call 等）
- `inputs/` — 各输入源 watcher（拖放、Telegram、Plaud、iCloud）

## 敏感文件（已 .gitignore，**不要 commit**）

- `backend/cookies.txt` — yt-dlp session cookies
- `backend/config.yaml` — 用户配置（含 Telegram token、Obsidian 路径等）
- `backend/.env` — 各种 API token
- `*.db` / `*.db-journal` — SQLite 状态

## 测试与 CI

- `backend/tests/` — pytest 单元测试
- GitHub Actions：`.github/workflows/` 已配 CI + release
- 跑测试：`cd backend && pytest`

## 协作原则（项目特有，全局规则之外）

- 改 pipeline 前先读 `pipeline.py` 顶部的状态机注释
- 加新输入源放 `backend/inputs/` 一个新文件，照现有模式写
- 加新场景摘要模板放 `backend/prompts/`
- 改 config schema 同时改 `config.example.yaml`，跑 `migrate-from-v1.py` 测一下
- 前端改完跑 `npm run build` 确认 Tauri 能打包

## 已知坑

- v1 数据目录的 SQLite 在 v2 跑的时候可能 lock，看到 `database is locked` 先停 backend 再操作
- macOS 给 backend 进程权限：System Settings → Privacy → Full Disk Access（否则读不到 iCloud）
- Tauri 打包后第一次启动会被 Gatekeeper 拦，需要右键 Open
