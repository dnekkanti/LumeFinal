"""
The Librarian agent.

Responsibilities:
  - Recursively scan a directory for .mov and .mp4 files
  - Generate 720p H.264 proxies via FFmpeg
  - Extract one hero frame per 2 seconds via FFmpeg
  - Compute SHA-256 checksum of source files (used as clip PK)
  - Write clips, hero_frames to SQLite
  - Yield progress log lines for the Thought Stream

All work is driven by an async generator so Reflex can yield state updates
in real time without blocking the UI.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Generator

from sqlalchemy.orm import Session

from lume.db.models import Clip, HeroFrame, Scene, get_engine

logger = __import__("logging").getLogger(__name__)

HERO_FRAME_INTERVAL = 2  # seconds between hero frames
PROXY_HEIGHT = 720
PROXY_CRF = 23


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    """
    Fast partial hash: SHA-256 of (first 2 MB + last 2 MB + file size).
    Avoids reading entire multi-GB video files for each clip.
    """
    h = hashlib.sha256()
    size = path.stat().st_size
    h.update(size.to_bytes(8, "little"))
    read_size = min(2 * chunk, size)
    with open(path, "rb") as f:
        h.update(f.read(read_size))
        if size > 2 * read_size:
            f.seek(-read_size, 2)
            h.update(f.read(read_size))
    return h.hexdigest()


# Unambiguous video-only extensions (no overlap with TypeScript .mts)
_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv",
    ".m2ts", ".mxf", ".r3d", ".braw", ".wmv", ".webm",
}

# Directories to always skip when scanning for video files
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "uploaded_files"}

def _scan_clips(source_dir: Path) -> list[Path]:
    """Return all video files under *source_dir* recursively."""
    files: list[Path] = []
    for f in source_dir.rglob("*"):
        # Skip known non-video directories
        if any(part in _SKIP_DIRS for part in f.parts):
            continue
        if f.is_file() and f.suffix.lower() in _VIDEO_EXTENSIONS:
            files.append(f)
    # Deduplicate (resolve symlinks / case-insensitive FS)
    seen: set[str] = set()
    unique: list[Path] = []
    for f in files:
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(f.resolve())
    return sorted(unique)


def _get_video_info(source: Path) -> dict:
    """
    Return {duration, width, height, orientation} via ffprobe.
    Falls back to safe defaults on failure.
    """
    info = {"duration": 0.0, "width": 0, "height": 0, "orientation": "landscape"}
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json",
                str(source),
            ],
            capture_output=True, text=True, timeout=30,
        )
        import json as _json
        data = _json.loads(result.stdout)
        streams = data.get("streams", [{}])
        fmt = data.get("format", {})
        w = int(streams[0].get("width", 0)) if streams else 0
        h = int(streams[0].get("height", 0)) if streams else 0
        dur = float(fmt.get("duration", 0.0))
        if h > 0 and w > 0:
            if w > h:
                orient = "landscape"
            elif h > w:
                orient = "portrait"
            else:
                orient = "square"
        else:
            orient = "landscape"
        info = {"duration": dur, "width": w, "height": h, "orientation": orient}
    except Exception:
        pass
    return info


def _probe_codec(source: Path) -> str:
    """Return the video codec name (e.g. 'hevc', 'h264') via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name",
             "-of", "default=noprint_wrappers=1", str(source)],
            capture_output=True, text=True, timeout=15,
        )
        for line in r.stdout.splitlines():
            if line.startswith("codec_name="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return "unknown"


def _generate_proxy(source: Path, proxy_path: Path) -> bool:
    """
    Encode a 720p H.264 proxy using VideoToolbox hardware acceleration on Mac
    (falls back to libx264 if unavailable).  Returns True on success.
    """
    proxy_path.parent.mkdir(parents=True, exist_ok=True)
    if proxy_path.exists():
        return True  # already generated

    codec = _probe_codec(source)

    # Build command — try VideoToolbox first (Mac hardware encoder, ~10x faster
    # for HEVC 4K), fall back to software libx264 if it errors.
    def _cmd(encoder: str) -> list[str]:
        cmd = ["ffmpeg", "-y"]
        # Use VideoToolbox hardware decoder for HEVC to speed up input
        if codec == "hevc":
            cmd += ["-hwaccel", "videotoolbox"]
        cmd += ["-i", str(source), "-vf", f"scale=-2:{PROXY_HEIGHT}",
                "-c:v", encoder, "-an", "-movflags", "+faststart"]
        if encoder == "h264_videotoolbox":
            cmd += ["-b:v", "4M"]          # VT uses bitrate not CRF
        else:
            cmd += ["-crf", str(PROXY_CRF), "-preset", "fast"]
        cmd += [str(proxy_path)]
        return cmd

    try:
        result = subprocess.run(
            _cmd("h264_videotoolbox"),
            capture_output=True, timeout=600,
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass

    # VideoToolbox unavailable or failed — fall back to libx264
    if proxy_path.exists():
        proxy_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            _cmd("libx264"),
            capture_output=True, timeout=600,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        if proxy_path.exists():
            proxy_path.unlink(missing_ok=True)
        return False


def _extract_hero_frames(
    source: Path,
    frames_dir: Path,
    clip_id: str,
    duration: float,
) -> list[tuple[Path, float]]:
    """
    Extract one JPEG hero frame every HERO_FRAME_INTERVAL seconds using a
    single ffmpeg call with the fps filter — much faster than one call per frame.
    Returns list of (frame_path, timestamp_seconds).
    """
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Check if all expected frames already exist (re-run idempotency)
    expected_timestamps = [
        round(i * HERO_FRAME_INTERVAL, 1)
        for i in range(max(1, int(duration / HERO_FRAME_INTERVAL)))
    ]
    existing = [(frames_dir / f"{clip_id}_{ts:.1f}.jpg", ts)
                for ts in expected_timestamps
                if (frames_dir / f"{clip_id}_{ts:.1f}.jpg").exists()]
    if len(existing) == len(expected_timestamps):
        return existing  # all frames already extracted

    # Single ffmpeg call: extract one frame every HERO_FRAME_INTERVAL seconds
    # Output pattern: <clip_id>_%04d.jpg  (1-indexed)
    tmp_pattern = frames_dir / f"{clip_id}_%04d.jpg"
    fps_rate = f"1/{HERO_FRAME_INTERVAL}"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source),
        "-vf", f"fps={fps_rate},scale=iw*min(1\\,1280/iw):ih*min(1\\,1280/iw)",
        "-q:v", "3",
        "-vsync", "vfr",
        str(tmp_pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600)

    if result.returncode != 0:
        return []

    # Rename sequentially-numbered outputs to timestamp-named files
    frames: list[tuple[Path, float]] = []
    for i, ts in enumerate(expected_timestamps, 1):
        seq_path = frames_dir / f"{clip_id}_{i:04d}.jpg"
        ts_path  = frames_dir / f"{clip_id}_{ts:.1f}.jpg"
        if seq_path.exists() and not ts_path.exists():
            seq_path.rename(ts_path)
        if ts_path.exists():
            frames.append((ts_path, ts))

    return frames


def _load_image_b64(path: Path) -> tuple[str, str] | None:
    """Return (base64_data, media_type) for a JPEG, or None if unreadable."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return data, "image/jpeg"
    except Exception:
        return None


def _name_scene_with_gemini(
    frame_paths: list[Path],
    idx: int,
    date: str,
    api_key: str,
) -> tuple[str, str]:
    """
    Send up to 3 hero frames to Gemini and get back a scene name + description.
    Returns (name, description). Falls back to rule-based names on any error.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")

        parts: list = [
            f"You are helping organize a video editor's footage library.\n"
            f"These frames are from clips filmed on {date} (group {idx}).\n"
            f"Return ONLY valid JSON (no markdown) with these two fields:\n"
            f'  "name": a short evocative scene name, max 5 words '
            f'(e.g. "Golden Hour Cliffside", "Rainy City Streets")\n'
            f'  "description": one sentence describing what is being filmed\n'
        ]
        for fp in frame_paths[:3]:
            result = _load_image_b64(fp)
            if result:
                b64, mime = result
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})

        if len(parts) == 1:
            return f"Scene {idx}", f"Footage from {date}"

        response = model.generate_content(parts)
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text.rstrip())
        data = json.loads(text)
        name = str(data.get("name", f"Scene {idx}"))[:60]
        desc = str(data.get("description", f"Footage from {date}"))[:200]
        return name, desc
    except Exception as exc:
        logger.warning("Scene naming failed for group %d: %s", idx, exc)
        return f"Scene {idx}: {date}", f"Footage from {date}"


def _cluster_scenes(
    engine,
    upload_root: Path,
    gemini_api_key: str | None,
) -> Generator[dict, None, None]:
    """
    Cluster all usable clips into scenes by file-mtime proximity,
    optionally name them with Gemini vision, and write Scene rows + scene_id
    back to each Clip.
    """
    def _ev(msg: str, error: bool = False) -> dict:
        return {
            "agent": "librarian", "message": msg,
            "clip_id": None, "done": False, "error": error,
        }

    with Session(engine) as session:
        clip_rows = session.query(Clip).filter(Clip.usable == 1).all()
        clip_data = [(c.id, c.source_path) for c in clip_rows]

    if not clip_data:
        yield _ev("No usable clips to cluster into scenes.")
        return

    yield _ev(f"Clustering {len(clip_data)} clip(s) into scenes by shoot day…")

    # Sort by file mtime
    timed: list[tuple[float, str, str]] = []
    for clip_id, source_path in clip_data:
        try:
            mtime = os.path.getmtime(source_path)
        except Exception:
            mtime = 0.0
        timed.append((mtime, clip_id, source_path))
    timed.sort(key=lambda x: x[0])

    # Group by 3-hour gaps
    THREE_HOURS = 3 * 3600
    groups: list[list[tuple[float, str, str]]] = []
    if timed:
        current: list[tuple[float, str, str]] = [timed[0]]
        for i in range(1, len(timed)):
            if timed[i][0] - timed[i - 1][0] > THREE_HOURS:
                groups.append(current)
                current = [timed[i]]
            else:
                current.append(timed[i])
        groups.append(current)

    yield _ev(f"Found {len(groups)} scene(s) — naming with Gemini…" if gemini_api_key
              else f"Found {len(groups)} scene(s) — using rule-based names (no Gemini key).")

    # Clear old scenes (re-cluster fresh)
    with Session(engine) as session:
        session.query(Scene).delete()
        session.commit()

    for idx, group in enumerate(groups, 1):
        clip_ids = [g[1] for g in group]
        first_mtime = group[0][0]
        from datetime import datetime as _dt
        shoot_date = _dt.fromtimestamp(first_mtime).strftime("%Y-%m-%d") if first_mtime > 0 else "Unknown"

        # Gather hero frames for naming
        frame_paths: list[Path] = []
        if gemini_api_key:
            with Session(engine) as session:
                for cid in clip_ids[:3]:
                    hf = session.query(HeroFrame).filter_by(clip_id=cid).first()
                    if hf:
                        frame_paths.append(upload_root / hf.frame_path)

        if gemini_api_key and frame_paths:
            name, desc = _name_scene_with_gemini(frame_paths, idx, shoot_date, gemini_api_key)
        else:
            name = f"Shoot Day {idx}"
            desc = f"{len(clip_ids)} clip(s) from {shoot_date}"

        with Session(engine) as session:
            scene = Scene(
                name=name,
                description=desc,
                shoot_date=shoot_date,
                clip_count=len(clip_ids),
            )
            session.add(scene)
            session.flush()
            scene_id = scene.id
            for cid in clip_ids:
                clip = session.get(Clip, cid)
                if clip:
                    clip.scene_id = scene_id
            session.commit()

        yield _ev(f"Scene {idx}/{len(groups)}: \"{name}\" — {len(clip_ids)} clip(s)")

    yield _ev(f"Scene clustering complete — {len(groups)} scene(s) identified.")


def run_librarian(
    source_dir: str,
    project_dir: str,
    db_path: str,
    gemini_api_key: str | None = None,
) -> Generator[dict, None, None]:
    """
    Synchronous generator that performs all Librarian work and yields
    log-dict events suitable for the Thought Stream.

    Each yielded dict has the shape:
        {
            "agent": "librarian",
            "message": str,          # human-readable log line
            "clip_id": str | None,   # set when a clip is processed
            "done": bool,            # True on the final yield
            "error": bool,           # True if the message is an error
        }

    The caller (Reflex event handler) runs this in a thread and pushes
    state updates via the async yielding mechanism.
    """
    source = Path(source_dir)
    project = Path(project_dir)
    proxies_dir = project / "proxies"
    proxies_dir.mkdir(exist_ok=True)

    # Hero frames go into Reflex's upload directory so they're served via
    # /_upload/ — the only route the browser knows how to reach on the backend.
    # Path: <cwd>/uploaded_files/lume_frames/<clip_id>/
    upload_root = Path.cwd() / "uploaded_files"
    frames_root = upload_root / "lume_frames"
    frames_root.mkdir(parents=True, exist_ok=True)

    engine = get_engine(db_path)

    yield {"agent": "librarian", "message": f"Scanning {source} for video files…", "clip_id": None, "done": False, "error": False}

    clips = _scan_clips(source)
    if not clips:
        yield {"agent": "librarian", "message": f"No video files found in {source}. Check that the source folder is correct and contains .mp4/.mov/.mts/.mkv/etc files.", "clip_id": None, "done": True, "error": False}
        return

    yield {"agent": "librarian", "message": f"Found {len(clips)} clip(s). Starting indexing.", "clip_id": None, "done": False, "error": False}

    for idx, clip_path in enumerate(clips, 1):
        # --- Checksum ---
        yield {"agent": "librarian", "message": f"[{idx}/{len(clips)}] Checksumming {clip_path.name}…", "clip_id": None, "done": False, "error": False}
        try:
            clip_id = _sha256(clip_path)
        except Exception as exc:
            yield {"agent": "librarian", "message": f"Checksum failed for {clip_path.name}: {exc}", "clip_id": None, "done": False, "error": True}
            continue

        with Session(engine) as session:
            existing = session.get(Clip, clip_id)
            if existing:
                yield {"agent": "librarian", "message": f"Already indexed: {clip_path.name} — skipping.", "clip_id": clip_id, "done": False, "error": False}
                continue

        # --- Duration / dimensions ---
        vinfo = _get_video_info(clip_path)
        duration = vinfo["duration"] or 0.0

        # --- Proxy ---
        proxy_name = f"{clip_id[:16]}_{clip_path.stem}_proxy.mp4"
        proxy_path = proxies_dir / proxy_name
        yield {"agent": "librarian", "message": f"[{idx}/{len(clips)}] Generating proxy for {clip_path.name}…", "clip_id": clip_id, "done": False, "error": False}
        try:
            proxy_ok = _generate_proxy(clip_path, proxy_path)
        except Exception as exc:
            proxy_ok = False
            yield {"agent": "librarian", "message": f"Proxy error for {clip_path.name}: {exc}", "clip_id": clip_id, "done": False, "error": True}
        if not proxy_ok:
            yield {"agent": "librarian", "message": f"Proxy generation failed for {clip_path.name} — clip still indexed.", "clip_id": clip_id, "done": False, "error": True}
            proxy_path = None  # type: ignore[assignment]

        # --- Hero frames ---
        yield {"agent": "librarian", "message": f"[{idx}/{len(clips)}] Extracting hero frames for {clip_path.name}…", "clip_id": clip_id, "done": False, "error": False}
        frame_pairs = _extract_hero_frames(
            source=clip_path,
            frames_dir=frames_root / clip_id,
            clip_id=clip_id,
            duration=duration,
        )

        # --- Write to DB ---
        with Session(engine) as session:
            clip = Clip(
                id=clip_id,
                source_path=str(clip_path),
                proxy_path=str(proxy_path) if proxy_path else None,
                duration_seconds=duration,
                width=vinfo["width"],
                height=vinfo["height"],
                orientation=vinfo["orientation"],
                has_people=-1,  # unknown until Scout runs
                created_at=datetime.now(timezone.utc).isoformat(),
                usable=1,
            )
            session.merge(clip)
            for frame_path, ts in frame_pairs:
                # Store the upload-relative key (lume_frames/<clip_id>/file.jpg)
                # so _reload_clips_sync can pass it to rx.get_upload_url().
                upload_key = str(frame_path.relative_to(upload_root))
                session.add(HeroFrame(
                    clip_id=clip_id,
                    frame_path=upload_key,
                    timestamp_seconds=ts,
                ))
            session.commit()

        yield {
            "agent": "librarian",
            "message": f"[{idx}/{len(clips)}] Indexed {clip_path.name} — {vinfo['orientation']} {vinfo['width']}×{vinfo['height']}, {duration:.1f}s, {len(frame_pairs)} hero frames.",
            "clip_id": clip_id,
            "done": False,
            "error": False,
        }

    # ── Scene clustering pass ─────────────────────────────────────────────────
    yield {"agent": "librarian", "message": "Starting scene clustering…",
           "clip_id": None, "done": False, "error": False}
    try:
        for ev in _cluster_scenes(engine, frames_root.parent, gemini_api_key):
            yield ev
    except Exception as exc:
        yield {"agent": "librarian", "message": f"Scene clustering failed: {exc}",
               "clip_id": None, "done": False, "error": True}

    yield {"agent": "librarian",
           "message": f"Librarian complete. {len(clips)} clip(s) processed.",
           "clip_id": None, "done": True, "error": False}
