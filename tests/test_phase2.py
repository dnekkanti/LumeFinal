"""
Phase 2 tests — Librarian agent and Reflex state.
Fully offline: no real FFmpeg calls, no real Git pushes.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lume.db.models import Clip, HeroFrame, create_db, get_engine
from sqlalchemy.orm import Session


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def project_dirs(tmp_dir):
    source = tmp_dir / "source"
    project = tmp_dir / "project"
    source.mkdir()
    project.mkdir()
    (project / "proxies").mkdir()
    (project / "hero_frames").mkdir()
    db_path = str(project / "lume.db")
    create_db(db_path)
    return source, project, db_path


# ── Scan tests ────────────────────────────────────────────────────────────────


class TestScan:
    def test_finds_mov_and_mp4(self, tmp_dir):
        from lume.agents.librarian import _scan_clips

        (tmp_dir / "a.mov").write_bytes(b"")
        (tmp_dir / "b.mp4").write_bytes(b"")
        (tmp_dir / "c.txt").write_bytes(b"")
        sub = tmp_dir / "sub"
        sub.mkdir()
        (sub / "d.MOV").write_bytes(b"")

        clips = _scan_clips(tmp_dir)
        names = {c.name.lower() for c in clips}
        assert "a.mov" in names
        assert "b.mp4" in names
        assert "d.mov" in names
        assert "c.txt" not in names

    def test_deduplicates(self, tmp_dir):
        from lume.agents.librarian import _scan_clips

        (tmp_dir / "x.mov").write_bytes(b"")
        clips = _scan_clips(tmp_dir)
        assert len(clips) == 1

    def test_empty_directory(self, tmp_dir):
        from lume.agents.librarian import _scan_clips

        assert _scan_clips(tmp_dir) == []


# ── Checksum tests ────────────────────────────────────────────────────────────


class TestChecksum:
    def test_sha256_deterministic(self, tmp_dir):
        from lume.agents.librarian import _sha256

        f = tmp_dir / "test.mov"
        f.write_bytes(b"hello lume")
        h1 = _sha256(f)
        h2 = _sha256(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_content_different_hash(self, tmp_dir):
        from lume.agents.librarian import _sha256

        a = tmp_dir / "a.mov"
        b = tmp_dir / "b.mov"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        assert _sha256(a) != _sha256(b)


# ── Proxy generation tests ────────────────────────────────────────────────────


class TestProxyGeneration:
    def test_skips_existing_proxy(self, tmp_dir):
        from lume.agents.librarian import _generate_proxy

        source = tmp_dir / "clip.mov"
        source.write_bytes(b"fake")
        proxy = tmp_dir / "proxy.mp4"
        proxy.write_bytes(b"existing")

        # Should return True without calling FFmpeg
        with patch("subprocess.run") as mock_run:
            result = _generate_proxy(source, proxy)
            assert result is True
            mock_run.assert_not_called()

    def test_ffmpeg_called_for_new_proxy(self, tmp_dir):
        from lume.agents.librarian import _generate_proxy

        source = tmp_dir / "clip.mov"
        source.write_bytes(b"fake")
        proxy = tmp_dir / "proxy.mp4"

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _generate_proxy(source, proxy)
            assert result is True
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "ffmpeg" in cmd[0]
            assert "720" in " ".join(cmd)

    def test_ffmpeg_failure_returns_false(self, tmp_dir):
        from lume.agents.librarian import _generate_proxy

        source = tmp_dir / "clip.mov"
        source.write_bytes(b"fake")
        proxy = tmp_dir / "proxy.mp4"

        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = _generate_proxy(source, proxy)
            assert result is False


# ── Hero frame extraction tests ───────────────────────────────────────────────


class TestHeroFrames:
    def test_extracts_at_correct_intervals(self, tmp_dir):
        from lume.agents.librarian import _extract_hero_frames, HERO_FRAME_INTERVAL

        frames_dir = tmp_dir / "frames"
        mock_result = MagicMock()
        mock_result.returncode = 0

        def _fake_run(cmd, **kwargs):
            # Create the output file to simulate FFmpeg success
            out = Path(cmd[-1])
            out.write_bytes(b"jpeg")
            return mock_result

        with patch("subprocess.run", side_effect=_fake_run):
            frames = _extract_hero_frames(
                source=tmp_dir / "clip.mov",
                frames_dir=frames_dir,
                clip_id="abc123",
                duration=6.0,
            )

        timestamps = [ts for _, ts in frames]
        assert 0.0 in timestamps
        assert HERO_FRAME_INTERVAL in timestamps
        assert 2 * HERO_FRAME_INTERVAL in timestamps
        assert len(timestamps) == 3  # 0, 2, 4 for duration=6

    def test_no_frames_for_zero_duration(self, tmp_dir):
        from lume.agents.librarian import _extract_hero_frames

        frames_dir = tmp_dir / "frames"
        with patch("subprocess.run"):
            frames = _extract_hero_frames(
                source=tmp_dir / "clip.mov",
                frames_dir=frames_dir,
                clip_id="abc",
                duration=0.0,
            )
        assert frames == []


# ── Full Librarian run_librarian generator ────────────────────────────────────


class TestRunLibrarian:
    def _make_fake_clip(self, source_dir: Path, name: str = "test.mov") -> Path:
        p = source_dir / name
        p.write_bytes(b"fake video content " + name.encode())
        return p

    def test_no_clips_yields_done(self, project_dirs):
        from lume.agents.librarian import run_librarian

        source, project, db_path = project_dirs
        events = list(run_librarian(str(source), str(project), db_path))
        assert events[-1]["done"] is True
        assert any("No .mov" in e["message"] for e in events)

    def test_yields_scanning_message(self, project_dirs):
        from lume.agents.librarian import run_librarian

        source, project, db_path = project_dirs
        self._make_fake_clip(source)
        mock_ffprobe = MagicMock()
        mock_ffprobe.stdout = "10.0\n"
        mock_ffprobe.returncode = 0
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.returncode = 0

        def _fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return mock_ffprobe
            # For hero frame extraction, write the output file
            if "-frames:v" in cmd:
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"jpeg")
            return mock_ffmpeg

        with patch("subprocess.run", side_effect=_fake_run):
            events = list(run_librarian(str(source), str(project), db_path))

        assert any("Scanning" in e["message"] for e in events)
        assert events[-1]["done"] is True

    def test_clip_written_to_db(self, project_dirs):
        from lume.agents.librarian import run_librarian

        source, project, db_path = project_dirs
        clip_path = self._make_fake_clip(source)

        mock_ffprobe = MagicMock()
        mock_ffprobe.stdout = "5.0\n"
        mock_ffprobe.returncode = 0
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.returncode = 0

        def _fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return mock_ffprobe
            if "-frames:v" in cmd:
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"jpeg")
            return mock_ffmpeg

        with patch("subprocess.run", side_effect=_fake_run):
            list(run_librarian(str(source), str(project), db_path))

        engine = get_engine(db_path)
        with Session(engine) as session:
            clips = session.query(Clip).all()
            assert len(clips) == 1
            assert clips[0].source_path == str(clip_path.resolve())
            assert clips[0].duration_seconds == 5.0
            frames = session.query(HeroFrame).filter_by(clip_id=clips[0].id).all()
            assert len(frames) > 0

    def test_skips_already_indexed(self, project_dirs):
        from lume.agents.librarian import run_librarian

        source, project, db_path = project_dirs
        self._make_fake_clip(source)

        mock_ffprobe = MagicMock()
        mock_ffprobe.stdout = "5.0\n"
        mock_ffprobe.returncode = 0
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.returncode = 0

        def _fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return mock_ffprobe
            if "-frames:v" in cmd:
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"jpeg")
            return mock_ffmpeg

        with patch("subprocess.run", side_effect=_fake_run):
            list(run_librarian(str(source), str(project), db_path))
            # Run again — same clip should be skipped
            events2 = list(run_librarian(str(source), str(project), db_path))

        assert any("skipping" in e["message"].lower() for e in events2)

    def test_all_events_have_agent_field(self, project_dirs):
        from lume.agents.librarian import run_librarian

        source, project, db_path = project_dirs
        events = list(run_librarian(str(source), str(project), db_path))
        for event in events:
            assert "agent" in event
            assert event["agent"] == "librarian"
            assert "message" in event
            assert "done" in event

    def test_proxy_failure_still_indexes_clip(self, project_dirs):
        """A failed proxy must not prevent the clip from being written to DB."""
        from lume.agents.librarian import run_librarian

        source, project, db_path = project_dirs
        self._make_fake_clip(source)

        mock_ffprobe = MagicMock()
        mock_ffprobe.stdout = "3.0\n"
        mock_ffprobe.returncode = 0
        mock_ffmpeg_fail = MagicMock()
        mock_ffmpeg_fail.returncode = 1  # proxy fails

        def _fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return mock_ffprobe
            if "-frames:v" in cmd:
                # Hero frame succeeds
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"jpeg")
                ok = MagicMock()
                ok.returncode = 0
                return ok
            return mock_ffmpeg_fail  # proxy fails

        with patch("subprocess.run", side_effect=_fake_run):
            events = list(run_librarian(str(source), str(project), db_path))

        engine = get_engine(db_path)
        with Session(engine) as session:
            clips = session.query(Clip).all()
            assert len(clips) == 1
            assert clips[0].proxy_path is None

        assert any(e["error"] for e in events)  # error log emitted
