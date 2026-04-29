"""
Colorist agent — Phase 4.

1. Accepts a natural language creative brief from the UI.
2. Uses Gemini to derive precise color grade parameters (lift/gamma/gain,
   saturation, contrast, temperature) as JSON.
3. Uses colour-science + numpy to bake a 33×33×33 3D LUT and write it as a
   .cube file into the project's /luts directory.
4. Uses FFmpeg to render before/after JPEG frames and saves them into
   uploaded_files/lume_luts/ so the UI can serve them.
5. Writes a row to the luts table and yields Thought Stream events.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import numpy as np

from sqlalchemy.orm import Session

from lume.db.models import Clip, HeroFrame, Score, Lut, get_engine

logger = logging.getLogger(__name__)

COLORIST_MODEL = "gemini-3.1-flash-lite-preview"

# ── Gemini prompt ─────────────────────────────────────────────────────────────

PARAMS_PROMPT = """\
You are a professional film colorist. Convert the following creative brief into \
precise color grading parameters for a 3D LUT.

Creative brief: "{prompt}"

Return ONLY a valid JSON object — no markdown, no explanation:
{{
  "lift":        [r, g, b],   // shadow offset, each -0.15 to 0.15, 0 = neutral
  "gamma":       [r, g, b],   // midtone power, each 0.5 to 2.0, 1.0 = neutral
  "gain":        [r, g, b],   // highlight multiplier, each 0.5 to 2.0, 1.0 = neutral
  "saturation":  <0.0–2.0>,   // 0 = B&W, 1.0 = neutral, 1.5 = vivid
  "contrast":    <0.5–2.0>,   // 0.5 = flat, 1.0 = neutral, 1.4 = punchy
  "temperature": <-1.0–1.0>,  // -1 = very cool/blue, 0 = neutral, 1 = very warm/amber
  "description": "..."        // one sentence describing the resulting look
}}
"""


# ── Parameter extraction ──────────────────────────────────────────────────────

def _prompt_to_params(prompt: str, api_key: str) -> dict:
    """Call Gemini to convert a creative brief into color grade parameters."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(COLORIST_MODEL)
    response = model.generate_content(PARAMS_PROMPT.format(prompt=prompt))
    text = response.text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text.rstrip())

    data = json.loads(text)

    def _clamp_list(lst, lo, hi):
        return [max(lo, min(hi, float(v))) for v in lst]

    return {
        "lift":        _clamp_list(data.get("lift",   [0, 0, 0]), -0.2, 0.2),
        "gamma":       _clamp_list(data.get("gamma",  [1, 1, 1]),  0.1, 3.0),
        "gain":        _clamp_list(data.get("gain",   [1, 1, 1]),  0.1, 3.0),
        "saturation":  max(0.0, min(2.5, float(data.get("saturation",  1.0)))),
        "contrast":    max(0.3, min(2.5, float(data.get("contrast",    1.0)))),
        "temperature": max(-1.0, min(1.0, float(data.get("temperature", 0.0)))),
        "description": str(data.get("description", "")),
    }


# ── Grade + LUT generation ────────────────────────────────────────────────────

def _apply_grade(table: np.ndarray, params: dict) -> np.ndarray:
    """
    Apply a cinematic grade to a (size, size, size, 3) identity RGB table.
    Operations applied in order: temperature → contrast → lift/gamma/gain → saturation.
    """
    rgb = table.copy()

    # 1. Temperature — shift R and B in opposite directions
    temp = float(params.get("temperature", 0.0))
    if temp != 0.0:
        rgb[..., 0] = np.clip(rgb[..., 0] + temp * 0.07, 0, 1)   # R warm
        rgb[..., 2] = np.clip(rgb[..., 2] - temp * 0.07, 0, 1)   # B cool

    # 2. Contrast — pivot around 0.5
    contrast = float(params.get("contrast", 1.0))
    if contrast != 1.0:
        rgb = np.clip(0.5 + (rgb - 0.5) * contrast, 0, 1)

    # 3. Lift / Gamma / Gain (CDL-style, per channel)
    lift  = params.get("lift",  [0.0, 0.0, 0.0])
    gamma = params.get("gamma", [1.0, 1.0, 1.0])
    gain  = params.get("gain",  [1.0, 1.0, 1.0])
    for ch in range(3):
        c = np.clip(rgb[..., ch] * float(gain[ch]) + float(lift[ch]), 0, 1)
        g = max(float(gamma[ch]), 0.01)
        rgb[..., ch] = np.clip(np.power(np.maximum(c, 1e-6), 1.0 / g), 0, 1)

    # 4. Saturation (Rec. 709 luminance coefficients)
    sat = float(params.get("saturation", 1.0))
    if sat != 1.0:
        lum = (
            0.2126 * rgb[..., 0]
            + 0.7152 * rgb[..., 1]
            + 0.0722 * rgb[..., 2]
        )[..., np.newaxis]
        rgb = np.clip(lum + (rgb - lum) * sat, 0, 1)

    return rgb.astype(np.float32)


def _generate_lut_cube(params: dict, output_path: Path) -> None:
    """Bake a 33×33×33 3D LUT and write it as a .cube file."""
    import colour

    size = 33
    lin = np.linspace(0, 1, size, dtype=np.float32)
    r, g, b = np.meshgrid(lin, lin, lin, indexing="ij")
    identity = np.stack([r, g, b], axis=-1)   # (33,33,33,3)

    graded = _apply_grade(identity, params)

    lut = colour.LUT3D(table=graded, name="Lume Grade")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    colour.io.write_LUT(lut, str(output_path))


# ── Before / after render ─────────────────────────────────────────────────────

def _render_before_after(
    hero_src: Path,
    cube_path: Path,
    before_out: Path,
    after_out: Path,
) -> bool:
    """Copy hero frame as 'before'; apply LUT via FFmpeg as 'after'."""
    before_out.parent.mkdir(parents=True, exist_ok=True)
    after_out.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(str(hero_src), str(before_out))

    # FFmpeg lut3d filter — escape Windows-style backslashes in path
    cube_str = str(cube_path).replace("\\", "/").replace(":", "\\:")
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(hero_src),
            "-vf", f"lut3d='{cube_str}'",
            "-q:v", "3",
            str(after_out),
        ],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0


# ── Main generator ────────────────────────────────────────────────────────────

def run_colorist(
    prompt: str,
    db_path: str,
    project_dir: str,
    gemini_api_key: str,
) -> Generator[dict, None, None]:
    """
    Generator yielding Thought Stream events.
    { "agent", "message", "lut_id": int|None, "done": bool, "error": bool }
    """
    def _ev(msg: str, lut_id=None, done=False, error=False) -> dict:
        return {"agent": "colorist", "message": msg,
                "lut_id": lut_id, "done": done, "error": error}

    engine = get_engine(db_path)
    upload_root = Path.cwd() / "uploaded_files"
    luts_dir   = Path(project_dir) / "luts"
    luts_dir.mkdir(exist_ok=True)

    # ── Step 1: derive parameters ─────────────────────────────────────────────
    yield _ev(f'Analyzing creative brief: \u201c{prompt}\u201d\u2026')
    try:
        params = _prompt_to_params(prompt, gemini_api_key)
    except Exception as exc:
        yield _ev(f"Parameter extraction failed: {exc}", error=True, done=True)
        return

    desc = params.pop("description", "")
    yield _ev(f"Parameters derived — {desc}")

    # ── Step 2: generate LUT ──────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cube_name = f"lume_{timestamp}.cube"
    cube_path = luts_dir / cube_name

    yield _ev(f"Baking 33×33×33 3D LUT → {cube_name}…")
    try:
        _generate_lut_cube(params, cube_path)
    except Exception as exc:
        yield _ev(f"LUT generation failed: {exc}", error=True, done=True)
        return

    # ── Step 3: pick a hero frame for before/after ────────────────────────────
    hero_abs: Path | None = None
    with Session(engine) as session:
        # Prefer the best-scored clip; fall back to first indexed clip
        best = (
            session.query(Score)
            .order_by(Score.score.desc())
            .first()
        )
        clip_id = best.clip_id if best else None
        if not clip_id:
            first_clip = session.query(Clip).first()
            clip_id = first_clip.id if first_clip else None
        if clip_id:
            frame = (
                session.query(HeroFrame)
                .filter_by(clip_id=clip_id)
                .order_by(HeroFrame.timestamp_seconds)
                .first()
            )
            if frame:
                hero_abs = upload_root / frame.frame_path

    # ── Step 4: render before / after ────────────────────────────────────────
    lut_upload_dir = upload_root / "lume_luts" / timestamp
    before_key = f"lume_luts/{timestamp}/before.jpg"
    after_key  = f"lume_luts/{timestamp}/after.jpg"
    before_out = upload_root / before_key
    after_out  = upload_root / after_key

    if hero_abs and hero_abs.exists():
        yield _ev("Rendering before/after comparison frames…")
        ok = _render_before_after(hero_abs, cube_path, before_out, after_out)
        if not ok:
            yield _ev("FFmpeg LUT render failed — frames will be missing.", error=True)
            before_key = after_key = ""
    else:
        yield _ev("No hero frame available for before/after render.", error=True)
        before_key = after_key = ""

    # ── Step 5: write to DB ───────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    with Session(engine) as session:
        lut_row = Lut(
            prompt=prompt,
            cube_path=str(cube_path),
            before_frame_path=before_key,
            after_frame_path=after_key,
            created_at=now,
        )
        session.add(lut_row)
        session.commit()
        lut_id = lut_row.id

    yield _ev(
        f'LUT \u201c{cube_name}\u201d ready. {desc}',
        lut_id=lut_id,
        done=True,
    )
