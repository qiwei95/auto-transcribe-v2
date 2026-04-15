"""去重引擎测试"""

from pathlib import Path

import pytest

from dedup import DedupDB


@pytest.fixture
def db(tmp_path):
    """创建临时数据库"""
    db = DedupDB(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def sample_file(tmp_path):
    """创建测试文件"""
    f = tmp_path / "test.m4a"
    f.write_bytes(b"fake audio content for testing" * 100)
    return f


@pytest.fixture
def sample_file_2(tmp_path):
    """创建另一个内容不同的测试文件"""
    f = tmp_path / "test2.m4a"
    f.write_bytes(b"different audio content here" * 100)
    return f


class TestFileHash:
    def test_consistent_hash(self, sample_file):
        """同一文件多次 hash 结果一致"""
        h1 = DedupDB.file_hash(sample_file)
        h2 = DedupDB.file_hash(sample_file)
        assert h1 == h2

    def test_hash_length(self, sample_file):
        """hash 前 16 位"""
        h = DedupDB.file_hash(sample_file)
        assert len(h) == 16

    def test_different_files_different_hash(self, sample_file, sample_file_2):
        """不同文件 hash 不同"""
        h1 = DedupDB.file_hash(sample_file)
        h2 = DedupDB.file_hash(sample_file_2)
        assert h1 != h2


class TestDedupCheck:
    def test_new_file_not_duplicate(self, db, sample_file):
        """新文件不是重复"""
        assert db.is_duplicate(sample_file) is False

    def test_marked_file_is_duplicate(self, db, sample_file):
        """标记后的文件是重复"""
        db.mark_processed(sample_file, source="manual", note_path="/test.md")
        assert db.is_duplicate(sample_file) is True

    def test_different_file_not_duplicate(self, db, sample_file, sample_file_2):
        """标记一个文件后，另一个内容不同的文件不是重复"""
        db.mark_processed(sample_file, source="manual")
        assert db.is_duplicate(sample_file_2) is False

    def test_same_content_different_name(self, db, sample_file, tmp_path):
        """同一内容不同文件名 = 重复（按内容 hash，不按文件名）"""
        db.mark_processed(sample_file, source="plaud")

        # 复制同内容到另一个文件名
        copy = tmp_path / "different-name.m4a"
        copy.write_bytes(sample_file.read_bytes())

        assert db.is_duplicate(copy) is True


class TestJobTracking:
    def test_add_and_get_job(self, db):
        job_id = db.add_job("test.m4a")
        assert job_id > 0

    def test_update_job_step(self, db):
        job_id = db.add_job("test.m4a")
        db.update_job(job_id, "transcribing")
        current = db.get_current_job()
        assert current is not None
        assert current["step"] == "transcribing"

    def test_done_job_not_current(self, db):
        job_id = db.add_job("test.m4a")
        db.update_job(job_id, "done")
        assert db.get_current_job() is None

    def test_today_done(self, db):
        job_id = db.add_job("test.m4a")
        db.update_job(job_id, "done", note_name="test-note.md")
        today = db.get_today_done()
        assert len(today) == 1
        assert today[0]["note_name"] == "test-note.md"

    def test_history_search(self, db):
        j1 = db.add_job("meeting-recording.m4a")
        db.update_job(j1, "done", note_name="2026-04-15-meeting-产品讨论.md")
        j2 = db.add_job("memo-idea.m4a")
        db.update_job(j2, "done", note_name="2026-04-15-memo-新想法.md")

        # 搜索
        results = db.get_history(search="产品")
        assert len(results) >= 1

    def test_step_progress(self, db):
        assert db.step_progress("transcribing") == "2/6 Transcribing"
        assert db.step_progress("done") == "Done"

    def test_delete_job(self, db):
        job_id = db.add_job("test.m4a")
        db.delete_job(job_id)
        assert db.get_current_job() is None
