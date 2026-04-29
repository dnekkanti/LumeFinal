"""
Audio Agent — matches clips to royalty-free ambient audio.

Strategy (in priority order):
1. Freesound.org CC0 search  — if FREESOUND_API_KEY is configured
2. Curated Archive.org library — always available, no key needed

Tags from Scout are mapped to sound categories, then matched against
the curated library and/or Freesound search results.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Generator

import requests
from sqlalchemy.orm import Session

from lume.db.models import AudioMatch, Clip, get_engine

logger = logging.getLogger(__name__)

FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
_ARCHIVE = "https://archive.org/download"

# ── Curated ambient sound library (Archive.org, all CC/public domain) ────────
# Organised by category — covers the most common Scout tag combinations.

CURATED_LIBRARY: list[dict] = [
    # ── Urban / Social ────────────────────────────────────────────────────────
    {
        "name": "Mall Ambient Crowd",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/ambient%20mall%20sounds.mp3",
        "duration": 131.0, "license": "CC BY 4.0",
        "tags": {"Indoor", "Urban", "Interview", "Portrait", "Close Up"},
    },
    {
        "name": "Street Musicians & People",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/street%20musicians%20ambient%20sounds.mp3",
        "duration": 120.0, "license": "CC BY 4.0",
        "tags": {"Outdoor", "Urban", "Action", "Documentary", "Handheld"},
    },
    {
        "name": "Street Crowd Ambiance",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/street%20musicians%20people%20sounds%201.mp3",
        "duration": 120.0, "license": "CC BY 4.0",
        "tags": {"Outdoor", "Urban", "Wide Shot", "Documentary"},
    },
    {
        "name": "Street Singers & Crowd",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/street%20singers%201.mp3",
        "duration": 95.0, "license": "CC BY 4.0",
        "tags": {"Outdoor", "Urban", "Action", "Interview"},
    },

    # ── Rain ──────────────────────────────────────────────────────────────────
    {
        "name": "Heavy Rainfall Ambiance",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/rain%201.mp3",
        "duration": 108.0, "license": "CC BY 4.0",
        "tags": {"Outdoor", "Nature", "Blue Hour", "Low Angle"},
    },
    {
        "name": "Light Rain Fading",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/rain%202%20easing%20off.mp3",
        "duration": 93.0, "license": "CC BY 4.0",
        "tags": {"Outdoor", "Nature", "Landscape"},
    },

    # ── Nature / Outdoor ──────────────────────────────────────────────────────
    {
        "name": "Nature & Distant Traffic",
        "preview_url": f"{_ARCHIVE}/nature-sounds-with-distant-traffic-d.-d.-teoli-jr."
                       "/Nature%20sounds%20with%20distant%20traffic%20D.D.Teoli%20Jr..mp3",
        "duration": 42.0, "license": "CC BY 4.0",
        "tags": {"Nature", "Outdoor", "Landscape", "Wide Shot", "Golden Hour"},
    },
    {
        "name": "Whale & Ocean Sounds",
        "preview_url": f"{_ARCHIVE}/whale-songs-whale-sound-effects"
                       "/Whale%20Songs%20%26%20Whale%20Sound%20Effects.mp3",
        "duration": 180.0, "license": "Public Domain",
        "tags": {"Nature", "Outdoor", "Landscape", "Blue Hour", "Wide Shot"},
    },

    # ── Night / Crickets ──────────────────────────────────────────────────────
    {
        "name": "Cricket Night Sounds 1",
        "preview_url": f"{_ARCHIVE}/animal-sfx/jangkrik%203.mp3",
        "duration": 94.0, "license": "CC BY 4.0",
        "tags": {"Night", "Outdoor", "Nature", "Slow Motion"},
    },
    {
        "name": "Cricket Night Sounds 2",
        "preview_url": f"{_ARCHIVE}/animal-sfx/jangkrik%204.mp3",
        "duration": 102.0, "license": "CC BY 4.0",
        "tags": {"Night", "Outdoor", "Nature", "Low Angle"},
    },

    # ── Indoor / Room Tone ────────────────────────────────────────────────────
    {
        "name": "Tram Interior Ambiance",
        "preview_url": f"{_ARCHIVE}/FreeSoundEffects2/inside%20moving%20tram%20sounds.mp3",
        "duration": 79.0, "license": "CC BY 4.0",
        "tags": {"Indoor", "Urban", "Documentary", "Handheld"},
    },
]

# ── Tag → category weight map ─────────────────────────────────────────────────
# Maps Scout tags to sets of curated-library tags for scoring

TAG_AFFINITIES: dict[str, set[str]] = {
    "Golden Hour":  {"Nature", "Outdoor", "Landscape"},
    "Blue Hour":    {"Nature", "Outdoor", "Blue Hour"},
    "Night":        {"Night", "Outdoor", "Nature"},
    "Indoor":       {"Indoor", "Urban", "Interview"},
    "Outdoor":      {"Outdoor", "Nature", "Urban"},
    "Interview":    {"Indoor", "Urban", "Interview"},
    "Action":       {"Action", "Urban", "Outdoor"},
    "Handheld":     {"Handheld", "Urban", "Outdoor"},
    "Stabilized":   {"Nature", "Landscape", "Wide Shot"},
    "Wide Shot":    {"Wide Shot", "Landscape", "Nature"},
    "Close Up":     {"Indoor", "Portrait", "Interview"},
    "Portrait":     {"Indoor", "Portrait", "Urban"},
    "Landscape":    {"Landscape", "Nature", "Wide Shot"},
    "Low Angle":    {"Low Angle", "Outdoor", "Nature"},
    "High Angle":   {"Wide Shot", "Landscape", "Urban"},
    "Slow Motion":  {"Slow Motion", "Nature", "Outdoor"},
    "Documentary":  {"Documentary", "Urban", "Outdoor"},
    "Nature":       {"Nature", "Outdoor", "Landscape"},
    "Urban":        {"Urban", "Outdoor", "Action"},
}


def _rank_curated(clip_tags: list[str], n: int = 3) -> list[dict]:
    """Score and rank curated sounds by tag overlap with the clip."""
    # Build a "want" set from clip tags via affinity map
    want: set[str] = set()
    for t in clip_tags:
        want.update(TAG_AFFINITIES.get(t, {t}))

    scored = []
    for sound in CURATED_LIBRARY:
        overlap = len(sound["tags"] & want)
        if overlap > 0:
            scored.append((overlap, sound))

    # Sort by overlap descending; if tie, preserve insertion order
    scored.sort(key=lambda x: -x[0])
    seen_names: set[str] = set()
    results = []
    for _, sound in scored:
        if sound["name"] not in seen_names:
            seen_names.add(sound["name"])
            results.append(sound)
        if len(results) >= n:
            break

    # Pad with top library items if not enough matches
    if len(results) < n:
        for sound in CURATED_LIBRARY:
            if sound["name"] not in seen_names:
                seen_names.add(sound["name"])
                results.append(sound)
            if len(results) >= n:
                break

    return results[:n]


# ── Freesound search (optional, requires API key) ────────────────────────────

def _freesound_search(keywords: str, api_key: str, max_results: int = 3) -> list[dict]:
    """Search Freesound for CC0 tracks. Returns [] on any failure."""
    # Build a short, clean query — Freesound prefers simple keywords
    clean = keywords.replace(",", " ").strip()[:80]

    # Try progressively broader queries if no results
    queries = [clean]
    words = [w.strip() for w in clean.split() if len(w.strip()) > 3]
    if len(words) >= 2:
        queries.append(" ".join(words[:3]))
    queries.append(words[0] if words else "ambient")

    for q in queries:
        try:
            resp = requests.get(
                FREESOUND_SEARCH_URL,
                params={
                    "query": q,
                    "filter": 'license:"Creative Commons 0"',
                    "fields": "id,name,previews,duration,license",
                    "page_size": max_results + 2,
                    "token": api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json().get("results", [])
            results = []
            for item in items:
                prev = item.get("previews", {})
                url = prev.get("preview-hq-mp3") or prev.get("preview-lq-mp3", "")
                if url:
                    results.append({
                        "freesound_id": item.get("id"),
                        "name": item.get("name", ""),
                        "preview_url": url,
                        "download_url": url,
                        "duration": float(item.get("duration", 0.0)),
                        "license": "CC0",
                    })
            if results:
                return results[:max_results]
        except Exception as exc:
            logger.warning("Freesound query '%s' failed: %s", q, exc)
    return []


# ── Keywords from Scout tags (no Gemini needed) ───────────────────────────────

_TAG_TO_AMBIENT: dict[str, str] = {
    "Golden Hour":  "warm afternoon birds outdoor ambient",
    "Blue Hour":    "dusk twilight ambient wind birds",
    "Night":        "night crickets quiet outdoor",
    "Indoor":       "indoor room tone quiet ambient",
    "Outdoor":      "outdoor wind birds ambient",
    "Interview":    "quiet indoor room tone",
    "Action":       "energetic movement crowd outdoor",
    "Handheld":     "walking footsteps outdoor ambient",
    "Wide Shot":    "wide open landscape wind",
    "Landscape":    "landscape wind nature ambient",
    "Nature":       "birds forest nature wind",
    "Urban":        "city street traffic crowd",
    "Documentary":  "documentary ambient crowd street",
    "Slow Motion":  "slow ambient wind nature cinematic",
    "Low Angle":    "ground level outdoor wind",
    "Portrait":     "quiet indoor person ambient",
    "Close Up":     "quiet intimate indoor",
}

def _tags_to_keywords(tags: list[str]) -> str:
    """Convert Scout tags to Freesound-friendly ambient keywords."""
    parts: list[str] = []
    seen: set[str] = set()
    for tag in tags[:4]:
        phrase = _TAG_TO_AMBIENT.get(tag, tag.lower())
        for word in phrase.split():
            if word not in seen:
                seen.add(word)
                parts.append(word)
    return " ".join(parts[:8]) or "ambient outdoor"


# ── Main generator ────────────────────────────────────────────────────────────

def run_audio_agent(
    db_path: str,
    gemini_api_key: str,
    freesound_api_key: str,
) -> Generator[dict, None, None]:
    """
    For each usable clip:
      1. Generate ambient keywords from Scout tags (no Gemini needed).
      2. Search Freesound if key is set → fall back to curated library.
      3. Always guarantee ≥ 2 results per clip from the curated library.
    """
    def _ev(msg: str, clip_id=None, done=False, error=False) -> dict:
        return {"agent": "librarian", "message": msg,
                "clip_id": clip_id, "done": done, "error": error}

    engine = get_engine(db_path)

    yield _ev("Audio Agent starting…")

    with Session(engine) as session:
        clips = session.query(Clip).filter(Clip.usable == 1).all()
        clip_data = [
            (c.id, c.source_path, [t.tag for t in c.tags])
            for c in clips
        ]

    if not clip_data:
        yield _ev("No usable clips found.", done=True)
        return

    has_freesound = bool(freesound_api_key and freesound_api_key.strip())
    source = "Freesound + curated library" if has_freesound else "curated library (no Freesound key)"
    yield _ev(f"Matching audio for {len(clip_data)} clip(s) using {source}…")

    matched = 0
    for idx, (clip_id, source_path, tags) in enumerate(clip_data, 1):
        name = Path(source_path).name
        yield _ev(f"[{idx}/{len(clip_data)}] Finding audio for {name}…", clip_id=clip_id)

        keywords = _tags_to_keywords(tags)

        # Try Freesound first (if key set), then curated fallback
        tracks: list[dict] = []
        if has_freesound:
            tracks = _freesound_search(keywords, freesound_api_key, max_results=3)
            if tracks:
                yield _ev(f"  Freesound: {len(tracks)} result(s) for '{keywords[:40]}'")
            time.sleep(0.5)  # pace Freesound requests

        # Always top up to 3 with curated sounds (deduplicated by name)
        curated = _rank_curated(tags, n=3)
        existing_names = {t.get("name", "") for t in tracks}
        for s in curated:
            if s["name"] not in existing_names and len(tracks) < 3:
                tracks.append({
                    "freesound_id": None,
                    "name": s["name"],
                    "preview_url": s["preview_url"],
                    "download_url": s["preview_url"],
                    "duration": s["duration"],
                    "license": s["license"],
                })

        # Write keywords + matches to DB
        with Session(engine) as session:
            clip_row = session.get(Clip, clip_id)
            if clip_row:
                clip_row.audio_keywords = keywords
            session.query(AudioMatch).filter_by(clip_id=clip_id).delete()
            for t in tracks:
                session.add(AudioMatch(
                    clip_id=clip_id,
                    freesound_id=t["freesound_id"],
                    name=t["name"],
                    preview_url=t["preview_url"],
                    download_url=t["download_url"],
                    duration=t["duration"],
                    license=t["license"],
                    assigned=0,
                    local_path=None,
                ))
            session.commit()

        track_names = ", ".join(t["name"][:25] for t in tracks)
        yield _ev(
            f"  {name} → {len(tracks)} track(s): {track_names}",
            clip_id=clip_id,
        )
        matched += 1

    yield _ev(f"Audio Agent complete — matched audio for {matched} clip(s).", done=True)
