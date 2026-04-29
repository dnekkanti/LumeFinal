"""
Watcher agent — Phase 7 (Watch Mode).

Monitors the project directory for changes to .fcpxml files. When FCP saves
a modified FCPXML, the watcher:

1. Parses old vs new XML and computes a structured diff:
     - clips added / removed / reordered
     - keyword (favorite) changes
     - duration changes
     - total clip count delta
2. Sends the diff to Gemini to generate a one-line semantic commit message.
3. Commits + pushes via the persistent Archivist registry.
4. Yields Thought Stream events back to the UI.

Lifecycle:
    start_watcher()  → returns a threading.Event (stop_event)
    stop_event.set() → tells the watchdog observer and the state loop to exit
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

WATCHER_MODEL = "gemini-3.1-flash-lite-preview"

# Namespace used by FCPXML 1.11 (no default namespace; attributes are bare)
_NS = {}


# ── FCPXML parsing ────────────────────────────────────────────────────────────

def _dur_seconds(s: str) -> float:
    """
    Parse an FCPXML duration string to float seconds.
    Handles: '215215/60060s', '21500/6000s', '100s', '0s'
    FCP often saves equivalent fractions differently, so we normalise to float.
    """
    s = s.strip().rstrip("s")
    if not s:
        return 0.0
    try:
        if "/" in s:
            num, den = s.split("/", 1)
            return float(num) / float(den)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _parse_spine_clips(xml_text: str) -> list[dict]:
    """
    Return an ordered list of clip descriptors from the <spine> element.
    Each dict: {name, ref, duration_s: float, keywords: list[str], luts: list[str]}
    Returns [] on any parse error.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    spine = root.find(".//{*}spine") or root.find(".//spine")
    if spine is None:
        return []

    clips = []
    for ac in spine:
        if not ac.tag.endswith("asset-clip"):
            continue
        name = ac.get("name", "")
        ref  = ac.get("ref", "")
        duration_s = _dur_seconds(ac.get("duration", "0s"))

        # Normalise keywords to lowercase so 'Favorite' == 'favorite'
        keywords = sorted({
            kw.get("value", "").lower().strip()
            for kw in ac
            if kw.tag.endswith("keyword")
        } - {""})

        # Detect applied LUT/filter effects (filter-video elements)
        luts = sorted({
            fv.get("name", "").strip()
            for fv in ac
            if fv.tag.endswith("filter-video") and fv.get("name", "")
        } - {""})

        clips.append({
            "name":       name,
            "ref":        ref,
            "duration_s": duration_s,
            "keywords":   keywords,
            "luts":       luts,
        })
    return clips


# ── Diff computation ─────────────────────────────────────────────────────────

_DURATION_THRESHOLD = 0.5  # seconds — ignore sub-half-second rounding differences

def diff_fcpxml(old_xml: str, new_xml: str) -> dict:
    """
    Compare two FCPXML strings and return a structured diff dict.
    Duration comparison is numeric (not string) to avoid false positives when
    FCP reformats rational fractions on save.
    """
    old_clips = _parse_spine_clips(old_xml)
    new_clips = _parse_spine_clips(new_xml)

    old_names = [c["name"] for c in old_clips]
    new_names = [c["name"] for c in new_clips]
    old_set   = set(old_names)
    new_set   = set(new_names)

    added   = [n for n in new_names if n not in old_set]
    removed = [n for n in old_names if n not in new_set]

    common_old = [n for n in old_names if n in new_set]
    common_new = [n for n in new_names if n in old_set]
    reordered  = common_old != common_new

    old_map = {c["name"]: c for c in old_clips}
    new_map = {c["name"]: c for c in new_clips}

    keyword_changes  = []
    duration_changes = []
    lut_changes      = []

    for name in old_set & new_set:
        oc = old_map[name]
        nc = new_map[name]

        # Keywords (already normalised to lowercase)
        old_kws = set(oc["keywords"])
        new_kws = set(nc["keywords"])
        added_kws   = sorted(new_kws - old_kws)
        removed_kws = sorted(old_kws - new_kws)
        if added_kws or removed_kws:
            keyword_changes.append({
                "clip": name, "added_kws": added_kws, "removed_kws": removed_kws,
            })

        # Duration — numeric comparison with threshold
        delta = abs(nc["duration_s"] - oc["duration_s"])
        if delta > _DURATION_THRESHOLD:
            duration_changes.append({
                "clip": name,
                "old_s": round(oc["duration_s"], 2),
                "new_s": round(nc["duration_s"], 2),
                "delta_s": round(nc["duration_s"] - oc["duration_s"], 2),
            })

        # LUT / filter-video changes
        old_luts = set(oc["luts"])
        new_luts = set(nc["luts"])
        added_luts   = sorted(new_luts - old_luts)
        removed_luts = sorted(old_luts - new_luts)
        if added_luts or removed_luts:
            lut_changes.append({
                "clip": name, "added": added_luts, "removed": removed_luts,
            })

    unchanged = (
        not added and not removed and not reordered
        and not keyword_changes and not duration_changes and not lut_changes
    )

    return {
        "added":            added,
        "removed":          removed,
        "reordered":        reordered,
        "keyword_changes":  keyword_changes,
        "duration_changes": duration_changes,
        "lut_changes":      lut_changes,
        "old_count":        len(old_clips),
        "new_count":        len(new_clips),
        "unchanged":        unchanged,
    }


# ── Gemini commit message ─────────────────────────────────────────────────────

_DIFF_PROMPT = """\
You are a film editor's assistant writing a Git commit message.
Given a structured diff of an FCPXML timeline, write ONE short commit message
(max 120 characters) that concisely describes what changed. Be specific.

Diff (JSON):
{diff_json}

Rules:
- Start with a past-tense verb (Reordered, Added, Removed, Marked, Trimmed, Applied, etc.)
- Mention clip names only if ≤ 3 clips changed; otherwise use counts
- If effects/keywords were added, mention them (e.g. "Applied LUT to 5 clips")
- If clips were removed, say how many and why if obvious from names
- Do NOT include markdown, quotes, or explanations — just the plain commit message
"""


def _summarize_diff(diff: dict, api_key: str) -> str:
    """Call Gemini to turn a diff dict into a one-line commit message."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(WATCHER_MODEL)

    diff_json = json.dumps(diff, indent=2)
    response = model.generate_content(_DIFF_PROMPT.format(diff_json=diff_json))
    msg = response.text.strip().strip('"').strip("'")
    # Truncate to 120 chars just in case
    return msg[:120] if msg else "Updated FCPXML timeline"


# ── Fallback: rule-based summary (no API call needed) ────────────────────────

def _rule_based_summary(diff: dict) -> str:
    """Generate a readable commit message from the diff without an LLM."""
    parts = []
    if diff["added"]:
        n = len(diff["added"])
        names = ", ".join(diff["added"][:3])
        parts.append(f"Added {n} clip(s): {names}" if n <= 3 else f"Added {n} clips")
    if diff["removed"]:
        n = len(diff["removed"])
        names = ", ".join(diff["removed"][:3])
        parts.append(f"Removed {n} clip(s): {names}" if n <= 3 else f"Removed {n} clips")
    if diff["reordered"]:
        parts.append("Reordered clips in timeline")
    if diff.get("lut_changes"):
        clips_with_luts = [lc["clip"] for lc in diff["lut_changes"] if lc["added"]]
        if clips_with_luts:
            n = len(clips_with_luts)
            lut_name = diff["lut_changes"][0]["added"][0] if diff["lut_changes"][0]["added"] else "LUT"
            parts.append(f"Applied {lut_name!r} to {n} clip(s)" if n <= 3
                         else f"Applied LUT to {n} clips")
    if diff["keyword_changes"]:
        # Only report non-trivial keyword changes (ignore pure casing normalisation)
        real_kw = [kc for kc in diff["keyword_changes"]
                   if kc["added_kws"] or kc["removed_kws"]]
        for kc in real_kw[:2]:
            if kc["added_kws"]:
                parts.append(f"Marked {kc['clip']!r} as {', '.join(kc['added_kws'])}")
            if kc["removed_kws"]:
                parts.append(f"Removed tag from {kc['clip']!r}")
    if diff["duration_changes"]:
        n = len(diff["duration_changes"])
        parts.append(f"Trimmed {n} clip(s)")
    return "; ".join(parts)[:120] if parts else "Updated FCPXML timeline"


# ── Bundle helpers ────────────────────────────────────────────────────────────

def _read_fcpxml_content(path: Path) -> str | None:
    """
    Read XML content from either:
    - a plain .fcpxml file, OR
    - a .fcpxmld bundle directory (FCP exports these when LUTs/effects are present).
      Inside the bundle, FCP puts the XML at Info.fcpxml or <stem>.fcpxml.
    Returns None on failure.
    """
    try:
        if path.suffix.lower() == ".fcpxmld" and path.is_dir():
            # Try Info.fcpxml first (FCP's default bundle layout)
            for candidate in ["Info.fcpxml", path.stem + ".fcpxml"]:
                xml_file = path / candidate
                if xml_file.exists():
                    return xml_file.read_text(encoding="utf-8", errors="replace")
            # Fall back: first .fcpxml file found inside
            for xml_file in path.glob("*.fcpxml"):
                return xml_file.read_text(encoding="utf-8", errors="replace")
            return None
        else:
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _iter_fcp_paths(project_dir: Path):
    """Yield all .fcpxml files and .fcpxmld bundle dirs in project_dir."""
    yield from project_dir.glob("*.fcpxml")
    yield from (p for p in project_dir.glob("*.fcpxmld") if p.is_dir())


# ── Watchdog observer ─────────────────────────────────────────────────────────

class _FCPXMLHandler:
    """
    Polls for changes to both .fcpxml flat files and .fcpxmld bundle directories.
    Called directly by the run_watcher loop.
    """

    def __init__(self, project_dir: Path, on_change):
        self.project_dir = project_dir
        self.on_change = on_change
        # Track mtime + content snapshot keyed by path
        self._snapshots: dict[Path, tuple[float, str]] = {}
        self._scan()

    def _scan(self) -> None:
        for p in _iter_fcp_paths(self.project_dir):
            content = _read_fcpxml_content(p)
            if content is None:
                continue
            try:
                mtime = p.stat().st_mtime
                self._snapshots[p] = (mtime, content)
            except OSError:
                pass

    def _find_best_old_xml(self, new_path: Path) -> str:
        """
        Find the best 'old' XML to diff against when FCP saves a bundle.
        Priority:
          1. Exact stem match (.fcpxml with same stem)
          2. Most-recently-modified .fcpxml snapshot (the last Lume export)
        """
        # Exact stem match
        for snapped_path, (_, content) in self._snapshots.items():
            if snapped_path.stem == new_path.stem:
                return content
        # Fall back to the most recently modified .fcpxml snapshot
        candidates = [
            (mtime, content)
            for snapped_path, (mtime, content) in self._snapshots.items()
            if snapped_path.suffix.lower() == ".fcpxml"
        ]
        if candidates:
            return max(candidates, key=lambda x: x[0])[1]
        return ""

    def poll(self) -> None:
        """Call periodically; fires on_change(path, old_xml, new_xml) for changed files."""
        for p in _iter_fcp_paths(self.project_dir):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue

            prev = self._snapshots.get(p)
            if prev is None:
                # New path — read content
                content = _read_fcpxml_content(p)
                if not content:
                    continue
                self._snapshots[p] = (mtime, content)

                # For a .fcpxmld bundle: find the best matching .fcpxml snapshot
                # so we get a real diff instead of treating it as brand-new.
                if p.suffix.lower() == ".fcpxmld":
                    old_xml = self._find_best_old_xml(p)
                    self.on_change(p, old_xml, content)
                else:
                    self.on_change(p, "", content)
                continue

            prev_mtime, prev_content = prev
            if mtime <= prev_mtime:
                continue

            new_content = _read_fcpxml_content(p)
            if not new_content:
                continue

            self._snapshots[p] = (mtime, new_content)
            if new_content != prev_content:
                self.on_change(p, prev_content, new_content)


# ── Main watcher generator ────────────────────────────────────────────────────

import os as _os

def _scan_dir(project_dir: Path) -> dict[str, tuple[float, str]]:
    """
    Return {path_str: (mtime, xml_content)} for every .fcpxml file and
    .fcpxmld bundle directory found directly inside project_dir.
    Uses os.scandir for reliability — no glob, no Path abstractions.
    """
    results: dict[str, tuple[float, str]] = {}
    try:
        with _os.scandir(str(project_dir)) as it:
            for entry in it:
                name_lower = entry.name.lower()
                if name_lower.endswith(".fcpxml") and entry.is_file(follow_symlinks=False):
                    try:
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                        content = Path(entry.path).read_text(encoding="utf-8", errors="replace")
                        results[entry.path] = (mtime, content)
                    except OSError:
                        pass
                elif name_lower.endswith(".fcpxmld") and entry.is_dir(follow_symlinks=False):
                    # Bundle: read Info.fcpxml inside
                    content = _read_fcpxml_content(Path(entry.path))
                    if content:
                        try:
                            mtime = entry.stat(follow_symlinks=False).st_mtime
                            # Also check mtime of Info.fcpxml inside the bundle
                            info = Path(entry.path) / "Info.fcpxml"
                            if info.exists():
                                mtime = max(mtime, info.stat().st_mtime)
                            results[entry.path] = (mtime, content)
                        except OSError:
                            pass
    except OSError:
        pass
    return results


def run_watcher(
    project_dir: str,
    gemini_api_key: str | None,
    stop_event: threading.Event,
    poll_interval: float = 3.0,
) -> Generator[dict, None, None]:
    """
    Generator yielding Thought Stream events.
    Runs until stop_event is set.
    { "agent", "message", "commit_message": str|None, "done": bool, "error": bool }
    """
    def _ev(msg: str, commit_message=None, done=False, error=False) -> dict:
        return {"agent": "watcher", "message": msg,
                "commit_message": commit_message, "done": done, "error": error}

    project_path = Path(project_dir)

    # Initial snapshot
    snapshots = _scan_dir(project_path)
    snap_names = [Path(p).name for p in snapshots]
    yield _ev(
        f"Watch mode active — watching {project_path.name}/ "
        f"({len(snapshots)} file(s) snapshotted: {', '.join(snap_names) or 'none'}). "
        f"Save your FCPXML from FCP into this folder to auto-commit."
    )

    while not stop_event.is_set():
        stop_event.wait(timeout=poll_interval)
        if stop_event.is_set():
            break

        current = _scan_dir(project_path)

        for path_str, (mtime, content) in current.items():
            name = Path(path_str).name
            prev = snapshots.get(path_str)

            if prev is None:
                # Brand new file — find best old XML to diff against
                old_xml = ""
                if name.lower().endswith(".fcpxmld"):
                    # Find most recent .fcpxml snapshot as the "before" state
                    fcpxml_snaps = [
                        (m, c) for p, (m, c) in snapshots.items()
                        if p.lower().endswith(".fcpxml")
                    ]
                    if fcpxml_snaps:
                        old_xml = max(fcpxml_snaps, key=lambda x: x[0])[1]

                snapshots[path_str] = (mtime, content)

                if not old_xml:
                    new_clips = _parse_spine_clips(content)
                    commit_msg = f"New FCPXML export: {Path(path_str).stem} ({len(new_clips)} clip(s))"
                    yield _ev(f"New file detected: {name} — {len(new_clips)} clip(s)")
                    yield _ev(f"Committing: \"{commit_msg}\"", commit_message=commit_msg)
                else:
                    yield _ev(f"New bundle detected: {name} — diffing against previous export…")
                    yield from _process_diff(path_str, old_xml, content, gemini_api_key, _ev)
                continue

            prev_mtime, prev_content = prev
            if mtime <= prev_mtime:
                continue
            if content == prev_content:
                snapshots[path_str] = (mtime, content)
                continue

            # Changed file
            snapshots[path_str] = (mtime, content)
            yield _ev(f"Change detected in {name} — diffing…")
            yield from _process_diff(path_str, prev_content, content, gemini_api_key, _ev)

    yield _ev("Watch mode stopped.", done=True)


def _process_diff(path_str, old_xml, new_xml, gemini_api_key, _ev):
    diff = diff_fcpxml(old_xml, new_xml)
    if diff["unchanged"]:
        yield _ev(f"No timeline changes found in {Path(path_str).name}")
        return

    delta = diff["new_count"] - diff["old_count"]
    sign = "+" if delta >= 0 else ""
    yield _ev(
        f"{Path(path_str).name}: {diff['new_count']} clips ({sign}{delta})"
    )

    if gemini_api_key:
        try:
            commit_msg = _summarize_diff(diff, gemini_api_key)
        except Exception as exc:
            logger.warning("Gemini summarize failed: %s", exc)
            commit_msg = _rule_based_summary(diff)
    else:
        commit_msg = _rule_based_summary(diff)

    yield _ev(f"Committing: \"{commit_msg}\"", commit_message=commit_msg)
