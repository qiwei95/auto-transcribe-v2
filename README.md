# Auto-Transcribe

Local AI transcription + smart summaries → Obsidian notes.  
Open source, free, cross-platform.

## Features

- 🎙️ 100% local transcription — audio never leaves your machine (faster-whisper with CUDA/MPS/CPU)
- 🤖 AI-powered scene classification & summaries (16 templates: meeting, memo, lecture, video, call, etc.)
- 📥 Multiple input sources: drag & drop, Telegram bot, Plaud recorder, iCloud sync
- 📝 Auto-saves to Obsidian vault as structured markdown with frontmatter
- 🖥️ Modern desktop UI with system tray, real-time progress via WebSocket
- 🔒 Privacy-first: transcription is 100% local, only summaries use Claude CLI
- 🔄 Smart dedup: SHA256 content hashing prevents duplicate processing across inputs

## Screenshots

<!-- TODO: Add screenshots -->

## Download

[Windows (.exe)](../../releases) | [macOS (.dmg)](../../releases) | [Linux (.AppImage)](../../releases)

## Quick Start (from source)

### Prerequisites

- Python 3.11+
- Node.js 18+
- Rust (for Tauri)
- ffmpeg
- Claude CLI: `npm install -g @anthropic-ai/claude-code`
- NVIDIA GPU (recommended), Apple Silicon, or CPU

### Backend

```bash
cd backend
pip install -e .
python main.py serve
```

### Desktop App

```bash
cd frontend
npm install
npm run tauri dev
```

### CLI Mode (no GUI)

```bash
cd backend
python main.py run recording.m4a video.mp4
```

## Configuration

Copy `backend/config.example.yaml` to `backend/config.yaml` and customize:

```yaml
base_dir: ~/auto-transcribe
obsidian_output: ~/Documents/Obsidian Vault/recording-notes
whisper_model: large-v3-turbo
whisper_language: zh
plaud_enabled: false
icloud_enabled: false
```

## Architecture

```
Tauri Desktop App
├── Svelte 5 + Tailwind UI (Dashboard / History / Settings)
│   └── HTTP + WebSocket (localhost:8765)
├── Python FastAPI Backend (sidecar)
│   ├── faster-whisper (local GPU transcription)
│   ├── Claude CLI (AI summarization)
│   ├── watchdog (file monitoring)
│   ├── SQLite (dedup + job tracking)
│   └── Input Sources
│       ├── Telegram Bot (links → audio/text)
│       ├── Plaud Cloud (auto-pull recordings)
│       ├── iCloud Sync (Mac only)
│       └── YouTube Subtitles (fast extraction)
└── System Tray (minimize to tray, status indicator)
```

## API

Backend exposes REST API + WebSocket at `http://127.0.0.1:8765`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Current processing status |
| `/api/history` | GET | Processing history (paginated, searchable) |
| `/api/today` | GET | Today's completed items |
| `/api/upload` | POST | Upload file to inbox |
| `/api/pause` | POST | Toggle pause/resume |
| `/api/config` | GET/PUT | Read/update configuration |
| `/api/inputs` | GET | Input source status |
| `/api/system` | GET | System info (GPU, platform) |
| `/ws` | WebSocket | Real-time processing progress |

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

112 tests covering config, dedup, transcription quality, summarizer parsing, and all 3 input sources.

## License

MIT
