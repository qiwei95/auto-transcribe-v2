#!/usr/bin/env python3
"""
内容去重引擎 — 基于 SHA256 content hash

三层去重设计:
  Layer 1: 入口层 — 各输入源自己记录已拉取的 ID (Plaud recording_id, Telegram message_id)
  Layer 2: inbox 层 — 对文件计算 SHA256，查 processed 表，hash 重复则跳过 (本模块)
  Layer 3: 输出层 — 检查 Obsidian 目标文件是否已存在
"""

import hashlib
import platform
import sqlite3
from datetime import datetime
from pathlib import Path


class DedupDB:
    """基于 SQLite 的内容去重 + 任务状态追踪"""

    # ── 处理步骤 ──
    STEPS = {
        "waiting": "Waiting",
        "extracting": "Extracting audio",
        "transcribing": "Transcribing",
        "classifying": "Classifying",
        "titling": "Generating title",
        "summarizing": "Summarizing",
        "saving": "Saving",
        "done": "Done",
        "failed": "Failed",
    }

    ACTIVE_STEPS = [
        "extracting", "transcribing", "classifying",
        "titling", "summarizing", "saving",
    ]

    # 每步预估耗时 (秒)，transcribing 按音频时长计算
    STEP_DURATIONS = {
        "extracting": 10,
        "transcribing": None,
        "classifying": 15,
        "titling": 15,
        "summarizing": 60,
        "saving": 5,
    }

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=5)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=3000")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_tables(self) -> None:
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT UNIQUE NOT NULL,
                original_filename TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                note_path TEXT DEFAULT '',
                processed_at TEXT NOT NULL,
                machine_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                content_hash TEXT DEFAULT '',
                step TEXT NOT NULL DEFAULT 'waiting',
                step_label TEXT NOT NULL DEFAULT 'Waiting',
                duration_sec REAL DEFAULT 0,
                note_name TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Layer 2: 内容去重 ──

    @staticmethod
    def file_hash(path: Path) -> str:
        """计算文件 SHA256 前 16 位"""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def is_duplicate(self, file_path: Path) -> bool:
        """检查文件是否已处理过（基于内容 hash）"""
        content_hash = self.file_hash(file_path)
        conn = self._connect()
        row = conn.execute(
            "SELECT id FROM processed WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        return row is not None

    def mark_processed(
        self, file_path: Path, source: str = "manual", note_path: str = "",
    ) -> None:
        """标记文件为已处理"""
        conn = self._connect()
        conn.execute(
            "INSERT OR IGNORE INTO processed "
            "(content_hash, original_filename, source, note_path, "
            " processed_at, machine_id) VALUES (?,?,?,?,?,?)",
            (
                self.file_hash(file_path),
                file_path.name,
                source,
                note_path,
                datetime.now().isoformat(),
                platform.node(),
            ),
        )
        conn.commit()

    # ── 任务状态追踪 ──

    def add_job(self, filename: str) -> int:
        """新增一个待处理任务，返回 job id"""
        now = datetime.now().isoformat()
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO jobs (filename, step, step_label, created_at, updated_at) "
            "VALUES (?, 'waiting', 'Waiting', ?, ?)",
            (filename, now, now),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_job(self, job_id: int, step: str, **kwargs: object) -> None:
        """更新任务状态"""
        label = self.STEPS.get(step, step)
        now = datetime.now().isoformat()
        sets = ["step = ?", "step_label = ?", "updated_at = ?"]
        vals: list[object] = [step, label, now]

        for key in ("duration_sec", "note_name", "error", "content_hash"):
            if key in kwargs:
                sets.append(f"{key} = ?")
                vals.append(kwargs[key])

        vals.append(job_id)
        conn = self._connect()
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()

    def get_current_job(self) -> dict | None:
        """获取当前正在处理的任务"""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM jobs WHERE step NOT IN ('done', 'failed', 'waiting') "
            "ORDER BY updated_at DESC LIMIT 1",
        ).fetchone()
        return dict(row) if row else None

    def get_today_done(self) -> list[dict]:
        """获取今日完成的任务"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE step = 'done' AND created_at LIKE ? "
            "ORDER BY updated_at DESC",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_history(
        self, limit: int = 50, offset: int = 0,
        type_filter: str = "", search: str = "",
    ) -> list[dict]:
        """获取处理历史（支持分页、类型筛选、搜索）"""
        conn = self._connect()
        query = "SELECT * FROM jobs WHERE step IN ('done', 'failed')"
        params: list[object] = []

        if type_filter:
            query += " AND note_name LIKE ?"
            params.append(f"%-{type_filter}-%")

        if search:
            query += " AND (filename LIKE ? OR note_name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def mark_stale_jobs(self, timeout_minutes: int = 30) -> None:
        """把超时的 job 标记为失败（崩溃恢复）"""
        conn = self._connect()
        conn.execute(
            "UPDATE jobs SET step = 'failed', step_label = 'Failed (timeout)', "
            "error = 'Processing timeout, possible crash', updated_at = ? "
            "WHERE step NOT IN ('done', 'failed', 'waiting') "
            "AND updated_at < datetime('now', ? || ' minutes')",
            (datetime.now().isoformat(), f"-{timeout_minutes}"),
        )
        conn.commit()

    def delete_job(self, job_id: int) -> None:
        """删除一条任务记录"""
        conn = self._connect()
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()

    def step_progress(self, step: str) -> str:
        """返回进度文字，如 '2/6 Transcribing'"""
        if step in self.ACTIVE_STEPS:
            idx = self.ACTIVE_STEPS.index(step) + 1
            total = len(self.ACTIVE_STEPS)
            return f"{idx}/{total} {self.STEPS[step]}"
        return self.STEPS.get(step, step)

    def estimate_remaining(self, job: dict) -> int | None:
        """估算剩余处理秒数"""
        step = job.get("step", "")
        if step not in self.ACTIVE_STEPS:
            return 0 if step in ("done", "failed") else None

        duration_sec = job.get("duration_sec") or 0

        def _step_time(s: str) -> float | None:
            dur = self.STEP_DURATIONS.get(s)
            if dur is not None:
                return dur
            if s == "transcribing":
                return duration_sec * 0.13 if duration_sec > 0 else None
            return None

        # 当前步骤已耗时间
        elapsed = 0.0
        updated_at = job.get("updated_at", "")
        if updated_at:
            try:
                updated = datetime.fromisoformat(updated_at)
                elapsed = (datetime.now() - updated).total_seconds()
            except (ValueError, TypeError):
                pass

        current_time = _step_time(step)
        if current_time is None:
            return None
        current_remaining = max(0, current_time - elapsed)

        # 后续步骤累加
        idx = self.ACTIVE_STEPS.index(step)
        future = 0.0
        for future_step in self.ACTIVE_STEPS[idx + 1:]:
            ft = _step_time(future_step)
            if ft is None:
                return None
            future += ft

        return int(current_remaining + future)
