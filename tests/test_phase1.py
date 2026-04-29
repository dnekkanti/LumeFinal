"""
Phase 1 tests — schema, config, and project init.
All tests are fully offline (no real GitHub calls, no FFmpeg).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from lume.config import (
    CONFIG_PATH,
    get_github_pat,
    get_active_project,
    list_projects,
    load_config,
    register_project,
    save_config,
    set_active_project,
    set_github_pat,
)
from lume.db.models import (
    Base,
    Clip,
    ClipLutAssignment,
    GitCommit,
    HeroFrame,
    Lut,
    Score,
    Tag,
    create_db,
    get_engine,
)
from lume.git_utils.archivist import Archivist, validate_github_remote
from lume.project import ProjectConfig, ProjectCreationError, create_project


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def tmp_db(tmp_dir):
    db_path = str(tmp_dir / "lume.db")
    engine = create_db(db_path)
    yield engine, db_path
    engine.dispose()


@pytest.fixture(autouse=True)
def isolate_config(tmp_dir, monkeypatch):
    """Redirect ~/.lume to a temp dir so tests never touch real config."""
    import lume.config as cfg_module

    fake_lume_dir = tmp_dir / ".lume"
    fake_lume_dir.mkdir()
    monkeypatch.setattr(cfg_module, "LUME_DIR", fake_lume_dir)
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", fake_lume_dir / "config.toml")


# ── Schema tests ──────────────────────────────────────────────────────────────


class TestSchema:
    def test_all_tables_created(self, tmp_db):
        engine, _ = tmp_db
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "clips",
            "hero_frames",
            "scores",
            "tags",
            "luts",
            "clip_lut_assignments",
            "git_commits",
        }
        assert expected == tables

    def test_clips_columns(self, tmp_db):
        engine, _ = tmp_db
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("clips")}
        assert cols == {"id", "source_path", "proxy_path", "duration_seconds", "created_at", "usable"}

    def test_clips_usable_default_is_1(self, tmp_db):
        engine, _ = tmp_db
        with Session(engine) as s:
            clip = Clip(id="abc123", source_path="/tmp/test.mov")
            s.add(clip)
            s.commit()
            fetched = s.get(Clip, "abc123")
            assert fetched.usable == 1

    def test_score_defaults(self, tmp_db):
        engine, _ = tmp_db
        with Session(engine) as s:
            clip = Clip(id="def456", source_path="/tmp/b.mov")
            s.add(clip)
            s.flush()
            score = Score(clip_id="def456")
            s.add(score)
            s.commit()
            fetched = s.get(Score, "def456")
            assert fetched.is_favorite == 0
            assert fetched.peak_moment == 0

    def test_foreign_keys_enforced(self, tmp_db):
        """hero_frames.clip_id must reference an existing clip."""
        engine, _ = tmp_db
        with Session(engine) as s:
            frame = HeroFrame(clip_id="nonexistent", frame_path="/tmp/f.jpg", timestamp_seconds=0.0)
            s.add(frame)
            with pytest.raises(Exception):
                s.commit()

    def test_clip_lut_assignment_composite_pk(self, tmp_db):
        engine, _ = tmp_db
        with Session(engine) as s:
            clip = Clip(id="ccc", source_path="/tmp/c.mov")
            lut = Lut(prompt="warm", cube_path="/tmp/warm.cube")
            s.add_all([clip, lut])
            s.flush()
            s.add(ClipLutAssignment(clip_id="ccc", lut_id=lut.id))
            s.commit()
            # Duplicate should raise
            s.add(ClipLutAssignment(clip_id="ccc", lut_id=lut.id))
            with pytest.raises(Exception):
                s.commit()

    def test_wal_mode_enabled(self, tmp_db):
        engine, _ = tmp_db
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode")).fetchone()
            assert result[0] == "wal"


# ── Config tests ──────────────────────────────────────────────────────────────


class TestConfig:
    def test_load_empty_config(self):
        cfg = load_config()
        assert cfg == {}

    def test_set_and_get_pat(self):
        set_github_pat("ghp_testtoken123")
        assert get_github_pat() == "ghp_testtoken123"

    def test_register_project_sets_active(self):
        register_project("proj-a", "/tmp/proj-a", "https://github.com/u/proj-a")
        register_project("proj-b", "/tmp/proj-b", "https://github.com/u/proj-b")
        active = get_active_project()
        assert active["name"] == "proj-b"

    def test_only_one_active_project(self):
        register_project("x", "/tmp/x", "https://github.com/u/x")
        register_project("y", "/tmp/y", "https://github.com/u/y")
        active_projects = [p for p in list_projects() if p.get("active")]
        assert len(active_projects) == 1

    def test_set_active_project(self):
        register_project("a", "/tmp/a", "https://github.com/u/a")
        register_project("b", "/tmp/b", "https://github.com/u/b")
        assert set_active_project("a") is True
        assert get_active_project()["name"] == "a"

    def test_set_active_project_not_found(self):
        assert set_active_project("ghost") is False

    def test_register_updates_existing(self):
        register_project("dup", "/tmp/dup-v1", "https://github.com/u/dup")
        register_project("dup", "/tmp/dup-v2", "https://github.com/u/dup")
        projects = [p for p in list_projects() if p["name"] == "dup"]
        assert len(projects) == 1
        assert projects[0]["path"] == "/tmp/dup-v2"


# ── Archivist tests ───────────────────────────────────────────────────────────


class TestArchivist:
    def test_init_repo_raises_without_remote(self, tmp_db, tmp_dir):
        engine, _ = tmp_db
        with Session(engine) as s:
            arch = Archivist(project_dir=tmp_dir, db_session=s)
            with pytest.raises(ValueError, match="remote URL is required"):
                arch.init_repo()

    def test_init_repo_creates_gitignore(self, tmp_db, tmp_dir):
        engine, _ = tmp_db
        with Session(engine) as s:
            arch = Archivist(
                project_dir=tmp_dir,
                db_session=s,
                remote_url="https://github.com/test/repo",
                github_pat=None,
            )
            # Skip remote validation / push in unit test
            with patch.object(arch, "_configure_remote"):
                arch.init_repo()
            gitignore = tmp_dir / ".gitignore"
            assert gitignore.exists()
            content = gitignore.read_text()
            assert "*.mov" in content
            assert "*.mp4" in content
            assert "proxies/" in content

    def test_commit_records_to_db(self, tmp_db, tmp_dir):
        engine, _ = tmp_db
        with Session(engine) as s:
            arch = Archivist(
                project_dir=tmp_dir,
                db_session=s,
                remote_url="https://github.com/test/repo",
                github_pat=None,
            )
            with patch.object(arch, "_configure_remote"):
                arch.init_repo()

            # Create a tracked file and commit it
            (tmp_dir / "test.fcpxml").write_text("<fcpxml/>")
            sha = arch.commit("TEST: example commit", paths=["test.fcpxml"])

            if sha:  # None means nothing was staged
                record = s.query(GitCommit).filter_by(sha=sha).first()
                assert record is not None
                assert "TEST:" in record.message
                assert record.pushed == 0

    def test_push_status_synced_when_empty(self, tmp_db, tmp_dir):
        engine, _ = tmp_db
        with Session(engine) as s:
            arch = Archivist(project_dir=tmp_dir, db_session=s)
            status = arch.push_status
            assert status["state"] == "synced"


# ── validate_github_remote tests ─────────────────────────────────────────────


class TestValidateGithubRemote:
    def test_invalid_url(self):
        ok, msg = validate_github_remote("https://notgithub.com/foo/bar", "pat")
        assert not ok

    def test_valid_response(self):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"permissions": {"push": True}}
            mock_get.return_value = mock_resp
            ok, msg = validate_github_remote("https://github.com/user/repo", "ghp_test")
            assert ok

    def test_no_push_permission(self):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"permissions": {"push": False}}
            mock_get.return_value = mock_resp
            ok, msg = validate_github_remote("https://github.com/user/repo", "ghp_test")
            assert not ok
            assert "push access" in msg

    def test_bad_pat(self):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_get.return_value = mock_resp
            ok, msg = validate_github_remote("https://github.com/user/repo", "bad")
            assert not ok
            assert "invalid" in msg.lower()


# ── create_project integration tests ─────────────────────────────────────────


class TestCreateProject:
    def _make_source_dir(self, tmp_dir: Path) -> Path:
        src = tmp_dir / "source"
        src.mkdir()
        return src

    def test_empty_name_raises(self, tmp_dir):
        with pytest.raises(ProjectCreationError, match="empty"):
            create_project(
                name="",
                source_directory=str(tmp_dir),
                remote_url="https://github.com/u/r",
                projects_root=tmp_dir / "projects",
            )

    def test_invalid_remote_raises(self, tmp_dir):
        src = self._make_source_dir(tmp_dir)
        with pytest.raises(ProjectCreationError, match="GitHub HTTPS"):
            create_project(
                name="myproj",
                source_directory=str(src),
                remote_url="git@github.com:user/repo.git",
                projects_root=tmp_dir / "projects",
            )

    def test_missing_source_dir_raises(self, tmp_dir):
        with pytest.raises(ProjectCreationError, match="does not exist"):
            create_project(
                name="myproj",
                source_directory=str(tmp_dir / "nonexistent"),
                remote_url="https://github.com/u/r",
                projects_root=tmp_dir / "projects",
            )

    def test_full_creation(self, tmp_dir):
        src = self._make_source_dir(tmp_dir)
        projects_root = tmp_dir / "projects"

        with (
            patch("lume.project.validate_github_remote", return_value=(True, "ok")),
            patch("lume.git_utils.archivist.Archivist._configure_remote"),
            patch("lume.git_utils.archivist.Archivist.start_push_worker"),
        ):
            cfg = create_project(
                name="test-project",
                source_directory=str(src),
                remote_url="https://github.com/u/test-project",
                github_pat="ghp_fake",
                projects_root=projects_root,
            )

        assert cfg.name == "test-project"
        assert cfg.db_path.exists()
        assert (cfg.project_dir / ".gitignore").exists()
        assert (cfg.project_dir / "luts").is_dir()
        assert (cfg.project_dir / "proxies").is_dir()

    def test_duplicate_project_name_raises(self, tmp_dir):
        src = self._make_source_dir(tmp_dir)
        projects_root = tmp_dir / "projects"

        with (
            patch("lume.project.validate_github_remote", return_value=(True, "ok")),
            patch("lume.git_utils.archivist.Archivist._configure_remote"),
            patch("lume.git_utils.archivist.Archivist.start_push_worker"),
        ):
            create_project(
                name="dup-project",
                source_directory=str(src),
                remote_url="https://github.com/u/dup",
                github_pat="ghp_fake",
                projects_root=projects_root,
            )
            with pytest.raises(ProjectCreationError, match="already exists"):
                create_project(
                    name="dup-project",
                    source_directory=str(src),
                    remote_url="https://github.com/u/dup",
                    github_pat="ghp_fake",
                    projects_root=projects_root,
                )

    def test_registered_in_config(self, tmp_dir):
        src = self._make_source_dir(tmp_dir)
        projects_root = tmp_dir / "projects"

        with (
            patch("lume.project.validate_github_remote", return_value=(True, "ok")),
            patch("lume.git_utils.archivist.Archivist._configure_remote"),
            patch("lume.git_utils.archivist.Archivist.start_push_worker"),
        ):
            create_project(
                name="config-test",
                source_directory=str(src),
                remote_url="https://github.com/u/config-test",
                github_pat="ghp_fake",
                projects_root=projects_root,
            )

        active = get_active_project()
        assert active is not None
        assert active["name"] == "config-test"
