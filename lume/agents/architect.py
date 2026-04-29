"""
Architect agent — Phase 5.

Reads clip scores, tags, and LUT assignments from SQLite and constructs a
valid FCPXML 1.11 file. Validates asset existence and duration consistency
before writing. Opens the output file in Finder on completion.

FCPXML structure:
  <resources>  — format, asset (one per clip), effect (one per unique LUT)
  <library>
    <event name="Lume Export">
      <project>
        <sequence>
          <spine>  — asset-clips placed end-to-end
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from urllib.parse import quote

from sqlalchemy.orm import Session

from lume.db.models import Clip, ClipLutAssignment, Lut, Score, get_engine

# ── Standard FPS table ────────────────────────────────────────────────────────
# Maps rounded fps → (frame_num, frame_den) where 1 frame = num/den seconds.
_FPS_TABLE = {
    23.976: (1001, 24024),
    24.0:   (100,  2400),
    25.0:   (100,  2500),
    29.97:  (1001, 30030),
    30.0:   (100,  3000),
    50.0:   (100,  5000),
    59.94:  (1001, 60060),
    60.0:   (100,  6000),
    120.0:  (100,  12000),
}

_DEFAULT_FPS  = 29.97
_DEFAULT_FPS_PAIR = _FPS_TABLE[_DEFAULT_FPS]
_DEFAULT_W, _DEFAULT_H = 1920, 1080


# ── ffprobe helpers ───────────────────────────────────────────────────────────

def _get_video_info(path: str) -> dict:
    """
    Return {width, height, fps, frame_num, frame_den} via ffprobe.
    Falls back to 1080p29.97 on failure.
    """
    import json, re

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        w = int(stream.get("width", _DEFAULT_W))
        h = int(stream.get("height", _DEFAULT_H))

        # r_frame_rate is a string like "30000/1001"
        rfr = stream.get("r_frame_rate", "30000/1001")
        num_s, den_s = rfr.split("/")
        fps_raw = int(num_s) / int(den_s)

        # Find closest standard fps
        fps = min(_FPS_TABLE.keys(), key=lambda k: abs(k - fps_raw))
        frame_num, frame_den = _FPS_TABLE[fps]
        return {"width": w, "height": h, "fps": fps,
                "frame_num": frame_num, "frame_den": frame_den}
    except Exception:
        return {"width": _DEFAULT_W, "height": _DEFAULT_H, "fps": _DEFAULT_FPS,
                "frame_num": _DEFAULT_FPS_PAIR[0], "frame_den": _DEFAULT_FPS_PAIR[1]}


def _seconds_to_fcp(seconds: float, frame_num: int, frame_den: int) -> str:
    """Convert seconds to an FCPXML rational duration string."""
    fps = frame_den / frame_num
    frames = round(seconds * fps)
    if frames == 0:
        return "0s"
    return f"{frames * frame_num}/{frame_den}s"


def _file_url(path: str) -> str:
    """Convert an absolute filesystem path to a file:// URL."""
    p = Path(path).resolve()
    # quote each path component individually
    parts = [quote(part, safe="") for part in p.parts[1:]]
    return "file:///" + "/".join(parts)


def _clip_uid(clip_id: str) -> str:
    """
    Derive a stable FCP asset UID from the clip's SHA-256 checksum.
    Format: 8-4-4-4-12 uppercase hex.
    """
    h = clip_id.upper().replace("-", "")[:32].ljust(32, "0")
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(clips_rows: list) -> tuple[list, list[str]]:
    """
    Validate each clip's source file and duration.
    Returns (valid_clips, error_messages).
    Clips with missing files or zero duration are excluded from the export.
    """
    valid, errors = [], []
    for clip in clips_rows:
        src = Path(clip.source_path)
        if not src.exists():
            errors.append(f"Source file missing: {src}")
            continue
        if not clip.duration_seconds or clip.duration_seconds <= 0:
            errors.append(f"Zero/null duration for {src.name} — clip excluded.")
            continue
        valid.append(clip)
    return valid, errors


# ── FCPXML builder ────────────────────────────────────────────────────────────

def _build_fcpxml(
    project_name: str,
    clips_data: list[dict],
    lut_paths: dict[int, str],   # lut_id → absolute cube path
    frame_num: int,
    frame_den: int,
    width: int,
    height: int,
) -> str:
    root = ET.Element("fcpxml", version="1.11")
    resources = ET.SubElement(root, "resources")

    # Shared format resource
    ET.SubElement(
        resources, "format",
        id="r1",
        frameDuration=f"{frame_num}/{frame_den}s",
        width=str(width),
        height=str(height),
        colorSpace="1-1-1 (Rec. 709)",
    )

    # Asset resources (one per clip)
    for cd in clips_data:
        asset = ET.SubElement(
            resources, "asset",
            id=cd["res_id"],
            name=cd["name"],
            uid=cd["uid"],
            duration=cd["duration_str"],
            hasVideo="1",
            hasAudio="1",
            format="r1",
            start="0s",
        )
        ET.SubElement(asset, "media-rep",
                      kind="original-media", src=cd["src_url"])

    # NOTE: Custom LUT effect UIDs are FCP-version-dependent and cannot be
    # reliably embedded in FCPXML. Apply the .cube file manually in FCP via
    # Effects → Color → Custom LUT after import.
    effect_id_map: dict[int, str] = {}

    # Event → Project → Sequence → Spine
    # No <library> wrapper: FCP will prompt to import into an existing open library.
    event = ET.SubElement(root, "event", name="Lume Export")
    project_el = ET.SubElement(event, "project", name=project_name)

    total_frames = sum(cd["frames"] for cd in clips_data)
    total_dur = f"{total_frames * frame_num}/{frame_den}s"

    sequence = ET.SubElement(
        project_el, "sequence",
        duration=total_dur,
        format="r1",
        tcStart="0s",
        tcFormat="NDF",
        audioLayout="stereo",
        audioRate="48k",
    )
    spine = ET.SubElement(sequence, "spine")

    offset_frames = 0
    for cd in clips_data:
        offset_str = f"{offset_frames * frame_num}/{frame_den}s"
        clip_el = ET.SubElement(
            spine, "asset-clip",
            name=cd["name"],
            ref=cd["res_id"],
            offset=offset_str,
            duration=cd["duration_str"],
            start="0s",
            format="r1",
        )

        # FCP Favorite
        if cd.get("is_favorite"):
            ET.SubElement(clip_el, "keyword",
                          start="0s",
                          duration=cd["duration_str"],
                          value="Favorite")

        # LUT note: .cube path is tracked in DB; apply in FCP via Effects → Color → Custom LUT

        offset_frames += cd["frames"]

    ET.indent(root, space="    ")
    xml_body = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n{xml_body}\n'


# ── Main generator ────────────────────────────────────────────────────────────

def run_architect(
    db_path: str,
    project_name: str,
    project_dir: str,
    clip_ids: list[str] | None = None,
) -> Generator[dict, None, None]:
    """
    Generator yielding Thought Stream events.
    { "agent", "message", "output_path": str|None, "done": bool, "error": bool }

    clip_ids: if provided, only export these specific clips (filtered selection).
              If None, export all usable clips.
    """
    def _ev(msg: str, output_path=None, done=False, error=False) -> dict:
        return {"agent": "architect", "message": msg,
                "output_path": output_path, "done": done, "error": error}

    engine = get_engine(db_path)

    yield _ev("Starting Architect — loading clips from database…")

    # ── Load clips (filtered or all) ──────────────────────────────────────────
    with Session(engine) as session:
        query = session.query(Clip).filter(Clip.usable == 1)
        if clip_ids is not None:
            query = query.filter(Clip.id.in_(clip_ids))
        clips_rows = query.all()

        # Preserve the filter order if clip_ids were given
        if clip_ids is not None:
            order = {cid: i for i, cid in enumerate(clip_ids)}
            clips_rows = sorted(clips_rows, key=lambda c: order.get(c.id, 999))
        score_map  = {r.clip_id: r for r in session.query(Score).all()}
        lut_assigns = session.query(ClipLutAssignment).all()
        lut_rows   = session.query(Lut).all()

        # Build lookup: clip_id → lut_id
        clip_to_lut: dict[str, int] = {a.clip_id: a.lut_id for a in lut_assigns}

        # If no assignments but LUTs exist, auto-assign latest LUT to all clips
        if not clip_to_lut and lut_rows:
            latest_lut = max(lut_rows, key=lambda r: r.id)
            clip_to_lut = {c.id: latest_lut.id for c in clips_rows}
            yield _ev(
                f"No LUT assignments found — auto-assigning latest LUT "
                f"({Path(latest_lut.cube_path).name}) to all clips."
            )

        lut_paths: dict[int, str] = {r.id: r.cube_path for r in lut_rows}

    if not clips_rows:
        yield _ev("No usable clips found. Run the Librarian first.", error=True, done=True)
        return

    yield _ev(f"Validating {len(clips_rows)} clip(s)…")

    # ── Validation ────────────────────────────────────────────────────────────
    valid_clips, errors = _validate(clips_rows)
    for err in errors:
        yield _ev(f"Validation warning: {err}", error=True)

    if not valid_clips:
        yield _ev("All clips failed validation — aborting export.", error=True, done=True)
        return

    yield _ev(
        f"Validation complete — {len(valid_clips)} clip(s) OK"
        + (f", {len(errors)} warning(s)." if errors else ".")
    )

    # ── Detect format from majority orientation ───────────────────────────────
    # Use width/height already stored on Clip rows to vote on orientation,
    # then probe a representative clip of the winning orientation for fps/frame rate.
    yield _ev("Detecting video format…")

    landscape_clips = [c for c in valid_clips if (c.width or 0) >= (c.height or 0)]
    portrait_clips  = [c for c in valid_clips if (c.width or 0) <  (c.height or 0)]
    # Pick majority; tie goes to landscape
    representative = (landscape_clips if len(landscape_clips) >= len(portrait_clips)
                      else portrait_clips)[0]
    fmt = _get_video_info(representative.source_path)

    # If the stored DB dimensions disagree with the probed file (e.g. rotated mp4),
    # trust the stored orientation and swap width/height to match.
    if representative.width and representative.height:
        db_is_landscape = representative.width >= representative.height
        probe_is_landscape = fmt["width"] >= fmt["height"]
        if db_is_landscape != probe_is_landscape:
            fmt["width"], fmt["height"] = fmt["height"], fmt["width"]

    yield _ev(
        f"Format: {fmt['width']}×{fmt['height']} @ {fmt['fps']}fps — "
        f"frame duration {fmt['frame_num']}/{fmt['frame_den']}s"
        f" (from {'landscape' if fmt['width'] >= fmt['height'] else 'portrait'} majority)"
    )

    frame_num, frame_den = fmt["frame_num"], fmt["frame_den"]

    # ── Build clip data ───────────────────────────────────────────────────────
    clips_data: list[dict] = []
    for i, clip in enumerate(valid_clips):
        score_row  = score_map.get(clip.id)
        is_fav     = bool(score_row and score_row.is_favorite)
        score_val  = score_row.score if score_row else -1

        duration_str = _seconds_to_fcp(clip.duration_seconds, frame_num, frame_den)
        fps = frame_den / frame_num
        frames = round(clip.duration_seconds * fps)

        clips_data.append({
            "res_id":       f"r{i + 2}",
            "name":         Path(clip.source_path).stem,
            "uid":          _clip_uid(clip.id),
            "src_url":      _file_url(clip.source_path),
            "duration_str": duration_str,
            "frames":       frames,
            "is_favorite":  is_fav,
            "score":        score_val,
            "lut_id":       clip_to_lut.get(clip.id),
        })

    fav_count = sum(1 for cd in clips_data if cd["is_favorite"])
    lut_count = sum(1 for cd in clips_data if cd.get("lut_id"))
    yield _ev(
        f"Building FCPXML — {len(clips_data)} clips, "
        f"{fav_count} favorite(s), {lut_count} LUT assignment(s)…"
    )

    # ── Generate FCPXML ───────────────────────────────────────────────────────
    try:
        xml_str = _build_fcpxml(
            project_name=project_name,
            clips_data=clips_data,
            lut_paths=lut_paths,
            frame_num=frame_num,
            frame_den=frame_den,
            width=fmt["width"],
            height=fmt["height"],
        )
    except Exception as exc:
        yield _ev(f"FCPXML build failed: {exc}", error=True, done=True)
        return

    # ── Write file ────────────────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_name  = f"{project_name}_lume_{timestamp}.fcpxml"
    out_path  = Path(project_dir) / out_name
    out_path.write_text(xml_str, encoding="utf-8")

    lut_note = f", {lut_count} LUT(s) tracked in DB — apply in FCP via Effects → Color → Custom LUT" if lut_count else ""
    yield _ev(
        f"Exported: {out_name}  ({len(valid_clips)} clips, {fav_count} favorites{lut_note})",
        output_path=str(out_path),
        done=True,
    )
