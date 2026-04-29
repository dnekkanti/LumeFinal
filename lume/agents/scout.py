"""
Scout agent — Phase 3.

Pass 1 (free):   FFmpeg blurdetect + idet pre-filter on proxies.
                 Clips that fail are marked usable=0 and skipped in Pass 2.
Pass 2 (Gemini): Grade surviving clips 0-10 on stability, focus, and lighting
                 using Gemini 1.5 Flash vision (free tier). Identify peak moments.
                 Auto-tag with aesthetic labels. Writes Score + Tag rows to SQLite.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Generator

from sqlalchemy.orm import Session

from lume.db.models import Clip, HeroFrame, Score, Tag, get_engine

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

BLUR_THRESHOLD = 0.60      # avg blur_amount above this → clip culled
INTERLACE_RATIO = 0.35     # (TFF+BFF) / total above this → clip culled
MAX_FRAMES_PER_CLIP = 3    # max hero frames sent to Gemini per clip

# ── Gemini scoring prompt (batch) ────────────────────────────────────────────

BATCH_SIZE = 3   # clips per API call — reduces 279 calls → 93

SCORING_PROMPT = """\
You are a professional cinematographer evaluating video clips.
You will receive frames from multiple clips, each labelled ===CLIP N: filename===.
Score EACH clip independently and return a JSON ARRAY — one object per clip, in order.

Scoring criteria per clip:
- score (0–10): Overall quality
- stability (0–10): Camera steadiness
- focus (0–10): Subject sharpness
- lighting (0–10): Exposure quality
- peak_moment (true/false): Visually compelling / emotionally resonant moment?
- has_people (true/false): At least one visible human in ANY frame?
- tags: ALL applicable from: Golden Hour, Blue Hour, Night, Indoor, Outdoor, Interview,
  Action, Handheld, Stabilized, Wide Shot, Close Up, Portrait, Landscape,
  Low Angle, High Angle, Slow Motion, Documentary, Nature, Urban

Respond ONLY with a valid JSON array — no markdown, no explanation:
[
  {"clip": 1, "score": <n>, "stability": <n>, "focus": <n>, "lighting": <n>,
   "peak_moment": <bool>, "has_people": <bool>, "tags": [...]},
  ...
]
"""


# ── Pass 1: FFmpeg pre-filter ─────────────────────────────────────────────────

def _prefilter_clip(proxy_path: str) -> tuple[bool, str]:
    """
    Run FFmpeg blurdetect + idet on the proxy (first 8 s only) in a SINGLE pass.
    Short window keeps Pass 1 fast (~0.5s per clip on proxies).
    Returns (passes: bool, reason: str).
    """
    p = Path(proxy_path)
    if not p.exists():
        return True, ""

    # One ffmpeg call: split → blur branch (downsampled to 0.5fps) + idet branch
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-threads", "2",       # limit decoder threads
            "-t", "4",             # only need 4s to detect blur/interlace
            "-i", str(p),
            "-filter_complex",
            # Scale down to 640px wide first — much faster on 4K/1080p proxies
            "[0:v]scale=640:-2[scaled];"
            "[scaled]split=2[a][b];"
            "[a]fps=0.5,blurdetect=high=0.01[blur_out];"
            "[b]idet[idet_out]",
            "-map", "[blur_out]",
            "-map", "[idet_out]",
            "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True, timeout=60,
    )
    stderr = result.stderr

    # ── Blur check ────────────────────────────────────────────────────────────
    blur_amounts = [float(m) for m in re.findall(r"blur_amount:([\d.]+)", stderr)]
    if blur_amounts:
        avg_blur = sum(blur_amounts) / len(blur_amounts)
        logger.debug("blur avg=%.3f for %s", avg_blur, p.name)
        if avg_blur > BLUR_THRESHOLD:
            return False, f"Too blurry (avg blur_amount={avg_blur:.3f} > {BLUR_THRESHOLD})"

    # ── Interlace check ───────────────────────────────────────────────────────
    m = re.search(
        r"Multi frame detection:\s+TFF:\s*(\d+)\s+BFF:\s*(\d+)\s+"
        r"Progressive:\s*(\d+)\s+Undetermined:\s*(\d+)",
        stderr,
    )
    if m:
        tff, bff, prog, undet = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        total = tff + bff + prog + undet
        if total > 0 and (tff + bff) / total > INTERLACE_RATIO:
            return (
                False,
                f"Interlaced content (TFF:{tff} BFF:{bff} of {total} frames, "
                f"ratio={((tff+bff)/total):.2f} > {INTERLACE_RATIO})",
            )

    return True, ""


# ── Pass 2: Gemini vision scoring ─────────────────────────────────────────────

# Uses the new google-genai SDK (google.generativeai is deprecated).
# Model options — each has its own quota pool:
#   gemini-2.5-flash-lite  — free tier, fast, good for batch scoring
#   gemini-2.5-flash       — free tier, higher quality
#   gemini-2.0-flash-lite  — free tier (separate pool, may be exhausted)
import os as _os
SCOUT_MODEL = _os.environ.get("LUME_SCOUT_MODEL", "gemini-2.5-flash-lite")


def _load_image_b64(path: Path) -> tuple[str, str] | None:
    """Return (base64_data, media_type) for a JPEG, or None if unreadable."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return data, "image/jpeg"
    except Exception as exc:
        logger.warning("Failed to read frame %s: %s", path, exc)
        return None


def _clamp(v: float) -> float:
    return round(max(0.0, min(10.0, float(v))), 2)

def _default_score() -> dict:
    return {"score": 5.0, "stability": 5.0, "focus": 5.0, "lighting": 5.0,
            "peak_moment": False, "has_people": False, "tags": []}

def _parse_score(data: dict) -> dict:
    return {
        "score":       _clamp(data.get("score", 5.0)),
        "stability":   _clamp(data.get("stability", 5.0)),
        "focus":       _clamp(data.get("focus", 5.0)),
        "lighting":    _clamp(data.get("lighting", 5.0)),
        "peak_moment": bool(data.get("peak_moment", False)),
        "has_people":  bool(data.get("has_people", False)),
        "tags":        [str(t) for t in data.get("tags", [])],
    }

def _score_batch_with_gemini(
    clips: list[tuple[str, list[Path]]],   # [(clip_name, [frame_paths]), ...]
    api_key: str,
) -> list[dict]:
    """
    Score a batch of clips in ONE Gemini call using the google-genai SDK.
    Returns a list of score dicts in the same order as `clips`.
    Falls back to default scores on parse errors.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    parts: list = [SCORING_PROMPT]
    clips_with_frames = []
    for i, (name, frame_paths) in enumerate(clips, 1):
        parts.append(f"\n===CLIP {i}: {name}===\n")
        added = 0
        for path in frame_paths[:MAX_FRAMES_PER_CLIP]:
            result = _load_image_b64(path)
            if result:
                b64, mime = result
                parts.append(types.Part.from_bytes(
                    data=base64.b64decode(b64),
                    mime_type=mime,
                ))
                added += 1
        clips_with_frames.append(added > 0)

    # If no frames at all, return defaults
    if not any(clips_with_frames):
        return [_default_score() for _ in clips]

    response = client.models.generate_content(model=SCOUT_MODEL, contents=parts)
    text = response.text.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text.rstrip())

    raw = json.loads(text)
    # Handle both array and single-object responses
    if isinstance(raw, dict):
        raw = [raw]

    results = []
    for i in range(len(clips)):
        if i < len(raw):
            results.append(_parse_score(raw[i]))
        else:
            results.append(_default_score())
    return results


# ── Main generator ────────────────────────────────────────────────────────────

def run_scout(db_path: str, gemini_api_key: str) -> Generator[dict, None, None]:
    """
    Synchronous generator yielding event dicts in the same shape as
    run_librarian — consumed by the Reflex background task in state.py.

    Each dict:
        { "agent", "message", "clip_id": str|None, "done": bool, "error": bool }
    """
    def _ev(msg: str, clip_id=None, done=False, error=False) -> dict:
        return {"agent": "scout", "message": msg,
                "clip_id": clip_id, "done": done, "error": error}

    engine = get_engine(db_path)
    upload_root = Path.cwd() / "uploaded_files"

    yield _ev("Starting Scout…")

    # ── Ensure pass1_done column exists (safe no-op if already present) ──────
    from sqlalchemy import text as _text
    with engine.connect() as _conn:
        try:
            _conn.execute(_text("ALTER TABLE clips ADD COLUMN pass1_done INTEGER DEFAULT 0"))
            _conn.commit()
        except Exception:
            pass  # column already exists

    # ── Load all currently-usable clips ──────────────────────────────────────
    with Session(engine) as session:
        usable = [
            (c.id, c.source_path, c.proxy_path)
            for c in session.query(Clip).filter(Clip.usable == 1).all()
        ]

    if not usable:
        yield _ev("No usable clips found. Run the Librarian first.", done=True)
        return

    # ── Pass 1: FFmpeg pre-filter ─────────────────────────────────────────────
    # Skip clips that are already scored (Pass 2 done) OR already passed Pass 1
    with Session(engine) as session:
        already_scored_ids = {row.clip_id for row in session.query(Score).all()}
        already_pass1_ids  = set(
            row[0] for row in session.execute(
                _text("SELECT id FROM clips WHERE pass1_done = 1")
            )
        )

    needs_pass1 = [
        (cid, sp, pp) for cid, sp, pp in usable
        if cid not in already_scored_ids and cid not in already_pass1_ids
    ]
    skipped_pass1 = len(usable) - len(needs_pass1)

    if needs_pass1:
        yield _ev(
            f"Pass 1: FFmpeg quality filter on {len(needs_pass1)} clip(s)"
            + (f" ({skipped_pass1} already checked, skipping)." if skipped_pass1 else ".")
        )
    else:
        yield _ev(f"Pass 1: all {len(usable)} clips already checked — skipping.")

    culled_count = 0
    for i, (clip_id, source_path, proxy_path) in enumerate(needs_pass1, 1):
        name = Path(source_path).name
        if i == 1 or i % 20 == 0:
            yield _ev(f"[Pass 1] {i}/{len(needs_pass1)} — checking quality…")

        if proxy_path:
            try:
                passes, reason = _prefilter_clip(proxy_path)
            except Exception as exc:
                yield _ev(f"[Pass 1] FFmpeg error for {name}: {exc}",
                          clip_id=clip_id, error=True)
                passes, reason = True, ""
        else:
            passes, reason = True, ""   # no proxy → let through

        with Session(engine) as session:
            clip = session.get(Clip, clip_id)
            if clip:
                clip.pass1_done = 1
                if not passes:
                    clip.usable = 0
                session.commit()

        if not passes:
            culled_count += 1
            yield _ev(f"[Pass 1] Culled: {name} — {reason}", clip_id=clip_id)

    if needs_pass1:
        yield _ev(
            f"Pass 1 complete — culled {culled_count} clip(s). "
            f"Starting Gemini scoring…"
        )

    # ── Pass 2: Gemini scoring (batched) ─────────────────────────────────────
    with Session(engine) as session:
        surviving = [
            (c.id, c.source_path)
            for c in session.query(Clip).filter(Clip.usable == 1).all()
            if not session.get(Score, c.id)
        ]

    if not surviving:
        yield _ev("All clips already scored or culled — nothing to do.", done=True)
        return

    total = len(surviving)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    yield _ev(
        f"Pass 2: Scoring {total} clip(s) in {n_batches} batches of {BATCH_SIZE} "
        f"({SCOUT_MODEL})…"
    )

    import time
    scored_count = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = surviving[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        # Resolve frame paths for each clip in the batch
        batch_inputs: list[tuple[str, list[Path]]] = []
        batch_clip_ids: list[str] = []
        for clip_id, source_path in batch:
            name = Path(source_path).name
            with Session(engine) as session:
                frame_keys = [
                    row.frame_path
                    for row in session.query(HeroFrame)
                    .filter_by(clip_id=clip_id)
                    .order_by(HeroFrame.timestamp_seconds)
                    .all()
                ]
            batch_inputs.append((name, [upload_root / k for k in frame_keys]))
            batch_clip_ids.append(clip_id)

        names_str = ", ".join(n for n, _ in batch_inputs)
        yield _ev(f"[Batch {batch_num}/{n_batches}] Scoring: {names_str}…")

        # ── Batch Gemini call with exponential-backoff retry ─────────────────
        results = None
        _max_attempts = 6
        for _attempt in range(_max_attempts):
            try:
                results = _score_batch_with_gemini(batch_inputs, gemini_api_key)
                break
            except Exception as exc:
                exc_str = str(exc)
                is_rate = (
                    "429" in exc_str
                    or "quota" in exc_str.lower()
                    or "rate" in exc_str.lower()
                    or "resource_exhausted" in exc_str.lower()
                )
                if not is_rate or _attempt == _max_attempts - 1:
                    yield _ev(
                        f"Gemini error (batch {batch_num}): {exc}",
                        error=True,
                    )
                    results = None
                    break
                _retry_match = re.search(
                    r"retry[_\s]delay.*?seconds.*?(\d+)", exc_str, re.IGNORECASE
                )
                _wait = int(_retry_match.group(1)) + 3 if _retry_match else min(15 * (2 ** _attempt), 120)
                yield _ev(
                    f"Rate limited — waiting {_wait}s (attempt {_attempt+1}/{_max_attempts})…"
                )
                time.sleep(_wait)

        if results is None:
            continue

        # ── Write results for each clip in the batch ──────────────────────────
        for (clip_id, source_path), result in zip(batch, results):
            name = Path(source_path).name
            with Session(engine) as session:
                is_fav = 1 if result["score"] >= 8.5 else 0
                score_row = session.get(Score, clip_id)
                if score_row:
                    score_row.score      = result["score"]
                    score_row.stability  = result["stability"]
                    score_row.focus      = result["focus"]
                    score_row.lighting   = result["lighting"]
                    score_row.is_favorite = is_fav
                    score_row.peak_moment = 1 if result["peak_moment"] else 0
                else:
                    session.add(Score(
                        clip_id=clip_id,
                        score=result["score"],
                        stability=result["stability"],
                        focus=result["focus"],
                        lighting=result["lighting"],
                        is_favorite=is_fav,
                        peak_moment=1 if result["peak_moment"] else 0,
                    ))
                clip_row = session.get(Clip, clip_id)
                if clip_row:
                    clip_row.has_people = 1 if result["has_people"] else 0
                session.query(Tag).filter_by(clip_id=clip_id).delete()
                for tag in result["tags"]:
                    session.add(Tag(clip_id=clip_id, tag=tag))
                session.commit()

            scored_count += 1
            peak_str   = " ★" if result["peak_moment"] else ""
            people_str = " 👤" if result["has_people"] else ""
            tags_str   = f"  [{', '.join(result['tags'])}]" if result["tags"] else ""
            yield _ev(
                f"  {name} → score {result['score']:.1f} "
                f"(S:{result['stability']:.1f} F:{result['focus']:.1f} "
                f"L:{result['lighting']:.1f}){peak_str}{people_str}{tags_str}",
                clip_id=clip_id,
            )

        # Pace between batches — 4s keeps us safely under 15 RPM
        time.sleep(4)

    yield _ev(
        f"Scout complete — scored {scored_count} clip(s), culled {culled_count}.",
        done=True,
    )
