"""
Lume Reflex application state.

All UI-visible state lives here.  Background agent work is dispatched via
@rx.event(background=True) async generators that yield state mutations
through `async with self`.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

import reflex as rx
from pydantic import BaseModel

from lume.config import get_active_project, get_gemini_api_key, get_github_pat
from lume.db.models import AudioMatch, Clip, ClipLutAssignment, HeroFrame, Lut, Score, Tag, GitCommit, Scene, get_engine
from lume.git_utils.archivist import get_or_create_archivist, _archivist_registry
from lume.project import ProjectConfig, ProjectCreationError, create_project
from sqlalchemy import text
from sqlalchemy.orm import Session


# ── Data models passed to the UI ──────────────────────────────────────────────

class LogLine(BaseModel):
    agent: str = ""
    message: str = ""
    error: bool = False
    ts: str = ""


class ClipCard(BaseModel):
    clip_id: str = ""
    filename: str = ""
    duration: float = 0.0
    score: float = -1.0      # -1 means not yet scored
    stability: float = -1.0
    focus: float = -1.0
    lighting: float = -1.0
    hero_frame: str = ""     # relative URL or empty
    proxy_path: str = ""     # absolute filesystem path to proxy .mp4
    tags: list[str] = []
    usable: bool = True
    orientation: str = "landscape"   # "landscape" | "portrait" | "square"
    has_people: int = -1             # -1 unknown, 0 no, 1 yes
    is_favorite: bool = False
    scene_id: int = -1


class ProjectEntry(BaseModel):
    name: str = ""
    path: str = ""
    remote: str = ""
    active: bool = False
    clip_count: int = 0
    fav_count: int = 0
    push_pending: int = 0
    last_commit_at: str = ""


class CommitEntry(BaseModel):
    sha: str = ""
    message: str = ""
    pushed: bool = False
    created_at: str = ""


class LutEntry(BaseModel):
    lut_id: int = 0
    prompt: str = ""
    description: str = ""
    before_frame: str = ""   # upload-relative key
    after_frame: str = ""    # upload-relative key
    created_at: str = ""


class DaySummary(BaseModel):
    date: str = ""           # "2026-04-05"
    label: str = ""          # "Today", "Yesterday", or formatted date
    commits: list[CommitEntry] = []
    summary: str = ""        # AI-generated one-liner, empty until generated


class SceneEntry(BaseModel):
    scene_id:    int  = 0
    name:        str  = ""
    description: str  = ""
    shoot_date:  str  = ""
    clip_count:  int  = 0


class AudioTrack(BaseModel):
    track_id:    int   = 0
    clip_id:     str   = ""
    clip_name:   str   = ""
    name:        str   = ""
    preview_url: str   = ""
    duration:    float = 0.0
    assigned:    bool  = False
    local_path:  str   = ""

class AudioGroup(BaseModel):
    clip_id:    str   = ""
    clip_name:  str   = ""
    hero_frame: str   = ""
    keywords:   str   = ""
    tracks:     list[AudioTrack] = []


class ContentGroup(BaseModel):
    name: str = ""
    icon: str = ""
    clips: list[ClipCard] = []


class TodoItem(BaseModel):
    item_id:       int  = 0
    text:          str  = ""
    done:          bool = False
    ai_generated:  bool = False
    agent_trigger: str  = ""   # "" | "librarian" | "scout" | "colorist" | "architect" | "audio"


# ── Default AI-suggested todos ─────────────────────────────────────────────────
_DEFAULT_AI_TODOS: list[TodoItem] = [
    TodoItem(item_id=1,  text="Index media files with Librarian",         done=False, ai_generated=True,  agent_trigger="librarian"),
    TodoItem(item_id=2,  text="Score and tag clips with Scout",            done=False, ai_generated=True,  agent_trigger="scout"),
    TodoItem(item_id=3,  text="Generate LUT color grades",                 done=False, ai_generated=True,  agent_trigger="colorist"),
    TodoItem(item_id=4,  text="Export FCPXML for Final Cut Pro",           done=False, ai_generated=True,  agent_trigger="architect"),
    TodoItem(item_id=5,  text="Find royalty-free audio for clips",         done=False, ai_generated=True,  agent_trigger="audio"),
]


# ── Watcher stop-event registry (module-level, survives state resets) ─────────
import threading as _threading
_watcher_stop_events: dict[str, _threading.Event] = {}


# ── Main app state ────────────────────────────────────────────────────────────

class LumeState(rx.State):
    # ── Project ──────────────────────────────────────────────────────────────
    project_name: str = ""
    project_dir: str = ""
    db_path: str = ""
    source_dir: str = ""
    github_remote: str = ""

    # Project creation form
    form_name: str = ""
    form_source_dir: str = ""
    form_remote_url: str = ""
    form_pat: str = ""
    form_error: str = ""
    creating_project: bool = False
    show_create_dialog: bool = False

    # ── Agent state ──────────────────────────────────────────────────────────
    librarian_running: bool = False
    librarian_done: bool = False
    scout_running: bool = False
    scout_done: bool = False
    colorist_running: bool = False
    architect_running: bool = False
    last_fcpxml_path: str = ""
    watcher_active: bool = False
    source_watcher_active: bool = False

    # ── Thought Stream ────────────────────────────────────────────────────────
    log_lines: list[LogLine] = []

    # ── Library panel ────────────────────────────────────────────────────────
    clips: list[ClipCard] = []
    vibe_min_score: float = 0.0   # Vibe Slider minimum score filter

    # ── Color Lab ────────────────────────────────────────────────────────────
    colorist_prompt: str = ""
    lut_history: list[LutEntry] = []

    # ── Version Timeline ─────────────────────────────────────────────────────
    commits: list[CommitEntry] = []
    push_status_state: str = "synced"   # "synced" | "pending" | "auth_failed"
    push_status_label: str = "Synced"
    push_pending_count: int = 0

    # ── Center tabs ──────────────────────────────────────────────────────────
    active_tab: str = "workspace"

    # ── Clip preview ──────────────────────────────────────────────────────────
    selected_clip_id: str = ""
    selected_clip_name: str = ""
    selected_clip_frames: list[str] = []   # upload-relative keys for hero frames

    # ── Projects panel ───────────────────────────────────────────────────────
    all_projects: list[ProjectEntry] = []
    show_projects_panel: bool = False
    timeline_collapsed: bool = False

    # ── Activity panel (bottom strip) ────────────────────────────────────────
    activity_panel_open: bool = False

    # ── Library filters ───────────────────────────────────────────────────────
    filter_show: str = "all"           # "all" | "people" | "nature"
    filter_orientation: str = "all"    # "all" | "landscape" | "portrait"
    filter_favorites: bool = False
    filter_high_quality: bool = False  # score >= 8.0

    # ── Library sort & tag filter ─────────────────────────────────────────────
    sort_by: str = "default"           # "default"|"score_desc"|"score_asc"|"duration_desc"|"name"
    filter_active_tags: list[str] = [] # tag names that must be present

    # ── Library content grouping ──────────────────────────────────────────────
    group_by_content: bool = False
    collapsed_content_groups: list[str] = []

    # ── Clip detail drawer ────────────────────────────────────────────────────
    show_clip_detail: bool = False
    detail_clip_id: str = ""

    # ── Settings panel ────────────────────────────────────────────────────────
    show_settings_panel: bool = False
    settings_gemini_key: str = ""
    settings_freesound_key: str = ""
    settings_saved: bool = False       # flash "Saved!" confirmation

    # ── Scout progress ────────────────────────────────────────────────────────
    scout_total: int = 0
    scout_scored: int = 0

    # ── Architect preview ─────────────────────────────────────────────────────
    show_architect_preview: bool = False
    architect_preview_clips: list[ClipCard] = []

    # backward-compat alias used internally
    filter_people: str = "all"         # kept so reset code doesn't crash

    # ── Edit Diary ────────────────────────────────────────────────────────────
    diary_entries: list[DaySummary] = []
    diary_generating: bool = False

    # ── Smart LUT ─────────────────────────────────────────────────────────────
    smart_lut_running: bool = False

    # ── Creative Suggestions ──────────────────────────────────────────────────
    creative_suggestions: str = ""
    creative_suggestions_running: bool = False

    # ── Best Clips Story ──────────────────────────────────────────────────────
    best_clips_story: str = ""
    best_clips_story_running: bool = False

    # ── Auth ──────────────────────────────────────────────────────────────────
    is_logged_in: bool = False
    login_username: str = ""
    login_password: str = ""
    login_error: str = ""

    # ── Scenes ────────────────────────────────────────────────────────────────
    scenes: list[SceneEntry] = []
    collapsed_scene_ids: list[int] = []

    # ── Audio Lab ─────────────────────────────────────────────────────────────
    audio_groups:          list[AudioGroup] = []
    audio_agent_running:   bool = False
    freesound_api_key_input: str = ""

    # ── Tasks (todo list) ─────────────────────────────────────────────────────
    todo_items:  list[TodoItem] = []
    todo_input:  str = ""

    # ── Computed ─────────────────────────────────────────────────────────────

    _NATURE_TAGS = {"Nature", "Outdoor", "Landscape", "Wildlife", "Forest", "Beach", "Mountain"}

    @rx.var
    def filtered_clips(self) -> list[ClipCard]:
        """Clips passing all active filters, sorted by sort_by."""
        result = []
        for c in self.clips:
            if c.score >= 0 and c.score < self.vibe_min_score:
                continue
            if self.filter_show == "people" and c.has_people != 1:
                continue
            if self.filter_show == "nature":
                clip_tags = set(c.tags)
                if not clip_tags.intersection(self._NATURE_TAGS):
                    continue
            if self.filter_orientation != "all" and c.orientation != self.filter_orientation:
                continue
            if self.filter_favorites and not c.is_favorite:
                continue
            if self.filter_high_quality and (c.score < 0 or c.score < 8.0):
                continue
            if self.filter_active_tags:
                clip_tag_set = set(c.tags)
                if not any(t in clip_tag_set for t in self.filter_active_tags):
                    continue
            result.append(c)

        if self.sort_by == "score_desc":
            result.sort(key=lambda c: c.score if c.score >= 0 else -1.0, reverse=True)
        elif self.sort_by == "score_asc":
            result.sort(key=lambda c: c.score if c.score >= 0 else 99.0)
        elif self.sort_by == "duration_desc":
            result.sort(key=lambda c: c.duration, reverse=True)
        elif self.sort_by == "name":
            result.sort(key=lambda c: c.filename.lower())
        return result

    @rx.var
    def grouped_clips(self) -> list[ContentGroup]:
        """Filtered clips bucketed into content categories (for grouped view)."""
        if not self.group_by_content or not self.filtered_clips:
            return []

        BUCKET_DEFS = [
            ("People & Portraits", "users",    {"Portrait", "Close Up", "Interview"}),
            ("Nature & Outdoors",  "tree-pine", {"Nature", "Landscape", "Outdoor", "Golden Hour", "Blue Hour", "Wide Shot"}),
            ("Urban & City",       "building-2", {"Urban", "Documentary", "Indoor"}),
            ("Action & Motion",    "zap",       {"Action", "Handheld", "Slow Motion", "Low Angle", "High Angle"}),
            ("Night",              "moon",      {"Night", "Blue Hour"}),
        ]

        assigned: set[str] = set()
        result: list[ContentGroup] = []

        for name, icon, tag_set in BUCKET_DEFS:
            group_clips: list[ClipCard] = []
            for clip in self.filtered_clips:
                if clip.clip_id in assigned:
                    continue
                clip_tag_set = set(clip.tags)
                is_people_group = name == "People & Portraits" and clip.has_people == 1
                if bool(tag_set & clip_tag_set) or is_people_group:
                    group_clips.append(clip)
                    assigned.add(clip.clip_id)
            if group_clips:
                result.append(ContentGroup(name=name, icon=icon, clips=group_clips))

        uncategorized = [c for c in self.filtered_clips if c.clip_id not in assigned]
        if uncategorized:
            result.append(ContentGroup(name="Other", icon="film", clips=uncategorized))

        return result

    @rx.var
    def filtered_clip_count(self) -> int:
        return len(self.filtered_clips)

    @rx.var
    def available_tags(self) -> list[str]:
        """All unique tags across all clips, sorted alphabetically."""
        all_tags: set[str] = set()
        for c in self.clips:
            all_tags.update(c.tags)
        return sorted(all_tags)

    @rx.var
    def scored_clip_count(self) -> int:
        return sum(1 for c in self.clips if c.score >= 0)

    @rx.var
    def score_buckets(self) -> list[dict]:
        """Clip counts in 5 score bands for histogram display."""
        labels = ["Unscored", "0\u20134", "4\u20136", "6\u20138", "8\u201310"]
        colors = ["rgba(160,80,220,0.2)", "#f04040", "#f0a820", "#40b0f0", "#40c840"]
        counts = [0, 0, 0, 0, 0]
        for c in self.clips:
            if c.score < 0:
                counts[0] += 1
            elif c.score < 4:
                counts[1] += 1
            elif c.score < 6:
                counts[2] += 1
            elif c.score < 8:
                counts[3] += 1
            else:
                counts[4] += 1
        max_count = max(counts) if any(counts) else 1
        return [
            {"label": labels[i], "count": counts[i], "color": colors[i],
             "pct": round(counts[i] / max_count * 100)}
            for i in range(5)
        ]

    @rx.var
    def last_log_message(self) -> str:
        if not self.log_lines:
            return ""
        last = self.log_lines[-1]
        return f"[{last.agent}] {last.message}"

    @rx.var
    def any_agent_running(self) -> bool:
        return (self.librarian_running or self.scout_running or
                self.colorist_running or self.architect_running or
                self.audio_agent_running)

    @rx.var
    def detail_clip(self) -> ClipCard:
        for c in self.clips:
            if c.clip_id == self.detail_clip_id:
                return c
        return ClipCard()

    @rx.var
    def people_detected_count(self) -> int:
        """Number of clips Scout has confirmed contain people."""
        return sum(1 for c in self.clips if c.has_people == 1)

    @rx.var
    def favorites_count(self) -> int:
        """Number of clips marked as favorite."""
        return sum(1 for c in self.clips if c.is_favorite)

    @rx.var
    def scout_has_run(self) -> bool:
        """True if at least one clip has a known has_people value (0 or 1)."""
        return any(c.has_people >= 0 for c in self.clips)

    @rx.var
    def has_project(self) -> bool:
        return bool(self.project_name)

    @rx.var
    def grouped_commits(self) -> list[DaySummary]:
        """Commits grouped by date, newest first, with AI summaries merged in."""
        from datetime import date as _date, timedelta
        today = _date.today().isoformat()
        yesterday = (_date.today() - timedelta(days=1)).isoformat()

        groups: dict[str, list[CommitEntry]] = {}
        for c in self.commits:
            day = (c.created_at or "")[:10] or "Unknown"
            groups.setdefault(day, []).append(c)

        # Build a lookup for existing AI summaries
        summary_map = {ds.date: ds.summary for ds in self.diary_entries}

        result: list[DaySummary] = []
        for day in sorted(groups.keys(), reverse=True):
            if day == today:
                label = "Today"
            elif day == yesterday:
                label = "Yesterday"
            else:
                label = day
            result.append(DaySummary(
                date=day,
                label=label,
                commits=groups[day],
                summary=summary_map.get(day, ""),
            ))
        return result

    @rx.var
    def diary_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.commits) > 0
            and not self.diary_generating
        )

    @rx.var
    def smart_lut_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.clips) > 0
            and not self.smart_lut_running
            and not self.colorist_running
        )

    @rx.var
    def best_clips(self) -> list[ClipCard]:
        """Top ~10% of scored clips (min 1, max 8), sorted by score descending."""
        scored = [c for c in self.clips if c.score >= 0 and c.usable]
        scored.sort(key=lambda c: c.score, reverse=True)
        top_n = max(1, min(8, round(len(scored) * 0.10) or 1))
        return scored[:top_n]

    @rx.var
    def creative_suggestions_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.clips) > 0
            and not self.creative_suggestions_running
        )

    @rx.var
    def best_clips_story_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.best_clips) > 0
            and not self.best_clips_story_running
        )

    @rx.var
    def audio_agent_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.clips) > 0
            and not self.audio_agent_running
        )

    @rx.var
    def todo_done_count(self) -> int:
        return sum(1 for item in self.todo_items if item.done)

    @rx.var
    def todo_total_count(self) -> int:
        return len(self.todo_items)

    @rx.var
    def todo_progress_pct(self) -> int:
        total = len(self.todo_items)
        if total == 0:
            return 0
        done = sum(1 for item in self.todo_items if item.done)
        return round(done / total * 100)

    @rx.var
    def librarian_enabled(self) -> bool:
        return self.has_project and not self.librarian_running

    @rx.var
    def architect_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.clips) > 0
            and not self.architect_running
        )

    @rx.var
    def colorist_enabled(self) -> bool:
        return (
            self.has_project
            and len(self.clips) > 0
            and not self.colorist_running
            and self.colorist_prompt.strip() != ""
        )

    @rx.var
    def scout_enabled(self) -> bool:
        return (
            self.has_project
            and self.librarian_done
            and not self.scout_running
            and len(self.clips) > 0
        )

    # ── Auth ─────────────────────────────────────────────────────────────────

    def set_login_username(self, value: str):
        self.login_username = value
        self.login_error = ""

    def set_login_password(self, value: str):
        self.login_password = value
        self.login_error = ""

    def login(self):
        from lume.config import load_config
        cfg = load_config()
        expected_user = cfg.get("auth", {}).get("username", "admin")
        expected_pass = cfg.get("auth", {}).get("password", "lume")
        if (self.login_username.strip() == expected_user and
                self.login_password == expected_pass):
            self.is_logged_in = True
            self.login_error = ""
            self.login_password = ""
            return rx.redirect("/")
        else:
            self.login_error = "Incorrect username or password."

    def login_on_enter(self, key: str):
        """Keyboard handler — submits login only when Enter is pressed."""
        if key == "Enter":
            return LumeState.login

    def logout(self):
        self.is_logged_in = False
        self.login_username = ""
        self.login_password = ""
        return rx.redirect("/login")

    def check_auth(self):
        """on_load guard for the main app page."""
        if not self.is_logged_in:
            return rx.redirect("/login")
        self.load_active_project()

    def check_already_logged_in(self):
        """on_load guard for the login page — skip if already authed."""
        if self.is_logged_in:
            return rx.redirect("/")

    # ── Explicit setters (required in Reflex ≥0.8.9) ─────────────────────────

    def set_form_name(self, value: str):
        self.form_name = value

    def set_form_source_dir(self, value: str):
        self.form_source_dir = value

    def set_form_remote_url(self, value: str):
        self.form_remote_url = value

    def set_form_pat(self, value: str):
        self.form_pat = value

    def noop(self):
        """No-op handler for placeholder buttons."""

    def set_sort_by(self, value: str):
        self.sort_by = value

    def toggle_filter_tag(self, tag: str):
        if tag in self.filter_active_tags:
            self.filter_active_tags = [t for t in self.filter_active_tags if t != tag]
        else:
            self.filter_active_tags = self.filter_active_tags + [tag]

    def clear_tag_filters(self):
        self.filter_active_tags = []

    def toggle_group_by_content(self):
        self.group_by_content = not self.group_by_content

    def toggle_content_group(self, name: str):
        if name in self.collapsed_content_groups:
            self.collapsed_content_groups = [n for n in self.collapsed_content_groups if n != name]
        else:
            self.collapsed_content_groups = self.collapsed_content_groups + [name]

    # ── Todo / task list ─────────────────────────────────────────────────────

    def set_todo_input(self, value: str):
        self.todo_input = value

    def add_todo(self):
        text = self.todo_input.strip()
        if not text:
            return
        max_id = max((item.item_id for item in self.todo_items), default=0)
        new_id = max(max_id + 1, 100)  # user items start at 100+
        self.todo_items = self.todo_items + [
            TodoItem(item_id=new_id, text=text, done=False, ai_generated=False, agent_trigger="")
        ]
        self.todo_input = ""

    def add_todo_on_enter(self, key: str):
        if key == "Enter":
            return LumeState.add_todo

    def toggle_todo(self, item_id: int):
        updated = []
        for item in self.todo_items:
            if item.item_id == item_id:
                updated.append(TodoItem(
                    item_id=item.item_id, text=item.text,
                    done=not item.done, ai_generated=item.ai_generated,
                    agent_trigger=item.agent_trigger,
                ))
            else:
                updated.append(item)
        self.todo_items = updated

    def delete_todo(self, item_id: int):
        self.todo_items = [item for item in self.todo_items if item.item_id != item_id]

    def open_clip_detail(self, clip_id: str):
        self.active_tab = "workspace"
        self.detail_clip_id = clip_id
        self.show_clip_detail = True
        self.selected_clip_id = clip_id
        for card in self.clips:
            if card.clip_id == clip_id:
                self.selected_clip_name = card.filename
                break
        # Load hero frames for keyframe strip in drawer
        if not self.db_path:
            return
        try:
            engine = get_engine(self.db_path)
            with Session(engine) as session:
                frames = (session.query(HeroFrame)
                    .filter_by(clip_id=clip_id)
                    .order_by(HeroFrame.timestamp_seconds).all())
                keys = [f.frame_path for f in frames]
                if len(keys) > 5:
                    step = len(keys) / 5
                    keys = [keys[int(i * step)] for i in range(5)]
                self.selected_clip_frames = keys
        except Exception:
            self.selected_clip_frames = []

    def close_clip_detail(self):
        self.show_clip_detail = False

    def toggle_activity_panel(self):
        self.activity_panel_open = not self.activity_panel_open

    def open_activity_panel(self):
        self.activity_panel_open = True

    def open_settings(self):
        # Pre-fill with current saved values
        from lume.config import get_gemini_api_key, get_freesound_api_key
        self.settings_gemini_key = get_gemini_api_key() or ""
        self.settings_freesound_key = get_freesound_api_key() or ""
        self.settings_saved = False
        self.show_settings_panel = True

    def close_settings(self):
        self.show_settings_panel = False

    def save_settings(self):
        from lume.config import set_gemini_api_key, set_freesound_api_key
        if self.settings_gemini_key.strip():
            set_gemini_api_key(self.settings_gemini_key.strip())
        if self.settings_freesound_key.strip():
            set_freesound_api_key(self.settings_freesound_key.strip())
        self.settings_saved = True

    def set_settings_gemini_key(self, value: str):
        self.settings_gemini_key = value
        self.settings_saved = False

    def set_settings_freesound_key(self, value: str):
        self.settings_freesound_key = value
        self.settings_saved = False

    def open_architect_preview(self):
        # Show filtered clips if filters are active, otherwise top-scored
        filtered = self.filtered_clips
        all_usable = [c for c in self.clips if c.usable]
        if len(filtered) < len(all_usable):
            # Filters are active — show exactly what will be exported
            self.architect_preview_clips = filtered[:20]
        else:
            scored = [c for c in self.clips if c.score >= 0 and c.usable]
            scored.sort(key=lambda c: c.score, reverse=True)
            self.architect_preview_clips = scored[:20]
        self.show_architect_preview = True

    def close_architect_preview(self):
        self.show_architect_preview = False

    # ── Project creation ─────────────────────────────────────────────────────

    def open_create_dialog(self):
        self.show_create_dialog = True
        self.form_error = ""

    def close_create_dialog(self):
        self.show_create_dialog = False

    @rx.event(background=True)
    async def submit_create_project(self):
        async with self:
            self.creating_project = True
            self.form_error = ""

        # Snapshot form values into locals before run_in_thread — same reason as
        # the Librarian thread: closures over StateProxy can trigger ImmutableStateError.
        _name = self.form_name
        _source = self.form_source_dir
        _remote = self.form_remote_url
        _pat = self.form_pat or None

        try:
            cfg: ProjectConfig = await rx.run_in_thread(
                lambda: create_project(
                    name=_name,
                    source_directory=_source,
                    remote_url=_remote,
                    github_pat=_pat,
                )
            )
        except ProjectCreationError as exc:
            async with self:
                self.form_error = str(exc)
                self.creating_project = False
            return
        except Exception as exc:
            async with self:
                self.form_error = f"Unexpected error: {exc}"
                self.creating_project = False
            return

        async with self:
            self.project_name = cfg.name
            self.project_dir = str(cfg.project_dir)
            self.db_path = str(cfg.db_path)
            self.source_dir = cfg.source_directory
            self.github_remote = cfg.remote_url
            self.creating_project = False
            self.show_create_dialog = False
            self.log_lines = [
                LogLine(
                    agent="archivist",
                    message=f"Project '{cfg.name}' created. Git repo initialised.",
                    ts=_now(),
                )
            ]
        await self._reload_commits()

    def load_active_project(self):
        """Called on page load — rehydrate from config if a project is active."""
        proj = get_active_project()
        if not proj:
            return
        project_dir = Path(proj["path"])
        db_path = project_dir / "lume.db"
        if not db_path.exists():
            return
        self.project_name = proj["name"]
        self.project_dir = str(project_dir)
        self.db_path = str(db_path)
        self.github_remote = proj.get("remote", "")
        self.source_dir = proj.get("source_directory", "")
        self._migrate_hero_frame_paths()
        self._reload_clips_sync()
        self._reload_commits_sync()
        self._reload_luts_sync()
        self._init_default_todos()
        # If clips are already indexed, treat Librarian as done so Scout is enabled
        if self.clips:
            self.librarian_done = True

    def refresh_library(self):
        """Manually reload clips from DB — useful after background indexing completes."""
        self._reload_clips_sync()
        if self.clips:
            self.librarian_done = True

    @rx.event(background=True)
    async def purge_bad_clips(self):
        """Remove any clips whose source_path is not a real video file."""
        if not self.db_path:
            return

        _db_path = self.db_path

        _REAL_VIDEO_EXTS = {
            ".mp4", ".mov", ".m4v", ".avi", ".mkv",
            ".m2ts", ".mxf", ".r3d", ".braw", ".wmv", ".webm",
        }

        async with self:
            self._append_log("librarian", "Purging non-video clips from library…")
            self.activity_panel_open = True

        def _do_purge():
            from lume.db.models import Clip, HeroFrame, Score, Tag, ClipLutAssignment, get_engine
            from sqlalchemy.orm import Session as _S
            from pathlib import Path as _P
            engine = get_engine(_db_path)
            removed = 0
            with _S(engine) as session:
                all_clips = session.query(Clip).all()
                for clip in all_clips:
                    ext = _P(clip.source_path).suffix.lower()
                    if ext not in _REAL_VIDEO_EXTS:
                        session.delete(clip)
                        removed += 1
                session.commit()
            return removed

        import asyncio
        removed = await asyncio.get_event_loop().run_in_executor(None, _do_purge)

        async with self:
            self._reload_clips_sync()
            self._append_log("librarian", f"Purged {removed} non-video file(s) from library ✓")
            if self.clips:
                self.librarian_done = True

    # ── Librarian ────────────────────────────────────────────────────────────

    @rx.event(background=True)
    async def run_librarian(self):
        if not self.project_name:
            return

        async with self:
            self.librarian_running = True
            self.librarian_done = False
            self.activity_panel_open = True
            self._append_log("librarian", "Starting Librarian…")
            if not self.source_dir:
                self._append_log("librarian", "No source folder set for this project. Please create a new project and set the source folder.", error=True)
                self.librarian_running = False
                return

        # Capture state values into plain locals NOW, before the thread starts.
        # self is a StateProxy in a background task — reading it from a non-async
        # thread is not safe; locals are plain strings with no proxy indirection.
        import asyncio

        _source_dir = self.source_dir
        _project_dir = self.project_dir
        _db_path = self.db_path

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream_worker():
            try:
                # Force fresh import so edits to librarian.py take effect
                import importlib, lume.agents.librarian as _lib_mod
                importlib.reload(_lib_mod)
                _gen = _lib_mod.run_librarian
                for event in _gen(
                    source_dir=_source_dir,
                    project_dir=_project_dir,
                    db_path=_db_path,
                    gemini_api_key=get_gemini_api_key(),
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:
                import traceback
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "agent": "librarian", "message": f"Worker crashed: {exc}\n{traceback.format_exc()[:400]}",
                    "clip_id": None, "done": True, "error": True,
                })
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        thread = threading.Thread(target=_stream_worker, daemon=True)
        thread.start()

        # Track newly indexed clips; reload UI every 5 new clips to reduce overhead
        _new_clips_since_reload = 0
        while True:
            event = await queue.get()
            if event is None:
                break
            is_skip = "skipping" in event.get("message", "").lower()
            is_new  = bool(event.get("clip_id")) and not is_skip
            async with self:
                self._append_log(
                    event["agent"],
                    event["message"],
                    error=event.get("error", False),
                )
                if is_new:
                    _new_clips_since_reload += 1
                    # Reload clips grid every 5 newly indexed clips
                    if _new_clips_since_reload % 5 == 0:
                        self._reload_clips_sync()

        # Final state update + semantic commit
        async with self:
            self.librarian_running = False
            self.librarian_done = True
            self._reload_clips_sync()
            self._auto_check_todos("librarian")

        await self._commit_and_push(
            f"ACTION: Indexing complete. RESULT: {len(self.clips)} clip(s) indexed."
        )

        # Auto-start the source folder watcher after indexing completes.
        # Yielding an event spec here turns run_librarian into an async generator,
        # which Reflex background tasks fully support.
        async with self:
            _already_watching = self.source_watcher_active
            _has_source = bool(self.source_dir)
        if _has_source and not _already_watching:
            yield LumeState.start_source_watcher()

    # ── Scout ─────────────────────────────────────────────────────────────────

    @rx.event(background=True)
    async def run_scout(self):
        if not self.project_name:
            return

        api_key = get_gemini_api_key()
        if not api_key:
            async with self:
                self._append_log(
                    "scout",
                    "Gemini API key not found. Set GOOGLE_API_KEY env var "
                    "or add it to ~/.lume/config.toml under [gemini] api_key.",
                    error=True,
                )
            return

        async with self:
            self.scout_running = True
            self.scout_done = False
            self.scout_total = 0
            self.scout_scored = 0
            self.activity_panel_open = True
            self._append_log("scout", "Starting Scout…")

        import asyncio

        _db_path = self.db_path
        _api_key = api_key

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream_worker():
            try:
                import importlib, lume.agents.scout as _scout_mod
                importlib.reload(_scout_mod)
                _gen = _scout_mod.run_scout
                for ev in _gen(db_path=_db_path, gemini_api_key=_api_key):
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
            except Exception as exc:
                import traceback
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "agent": "scout",
                    "message": f"Scout worker crashed: {exc}\n{traceback.format_exc()[:400]}",
                    "clip_id": None, "done": True, "error": True,
                })
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=_stream_worker, daemon=True)
        thread.start()

        while True:
            ev = await queue.get()
            if ev is None:
                break
            # Only reload clips when a score has been written (Pass 2 events
            # have clip_id set AND message contains "→ score").
            # Pass 1 "Checking" events don't change scores so skip the reload.
            is_scored = bool(ev.get("clip_id")) and "→" in ev.get("message", "")
            async with self:
                self._append_log(
                    ev["agent"],
                    ev["message"],
                    error=ev.get("error", False),
                )
                if is_scored:
                    self.scout_scored += 1
                    self._reload_clips_sync()

        async with self:
            self.scout_running = False
            self.scout_done = True
            self._reload_clips_sync()
            self._auto_check_todos("scout")

        # Read counts directly from DB — self.clips may be stale outside async with self
        _db_path = self.db_path
        def _counts():
            from lume.db.models import Score as ScoreModel
            eng = get_engine(_db_path)
            with Session(eng) as s:
                culled = s.query(Clip).filter(Clip.usable == 0).count()
                scored = s.query(ScoreModel).count()
                favs   = s.query(ScoreModel).filter(ScoreModel.is_favorite == 1).count()
            return culled, scored, favs
        culled, scored, favs = await rx.run_in_thread(_counts)
        await self._commit_and_push(
            f"ACTION: Scouting. RESULT: Scored {scored} clips, "
            f"culled {culled}, {favs} favorite(s)."
        )

    # ── Colorist ──────────────────────────────────────────────────────────────

    @rx.event(background=True)
    async def run_colorist(self):
        if not self.project_name:
            return

        api_key = get_gemini_api_key()
        if not api_key:
            async with self:
                self._append_log("colorist", "Gemini API key not found.", error=True)
            return

        import asyncio

        _db_path = self.db_path
        _project_dir = self.project_dir
        _prompt = self.colorist_prompt
        _api_key = api_key

        async with self:
            self.colorist_running = True
            self.activity_panel_open = True
            self._append_log("colorist", f'Starting Colorist \u2014 \u201c{_prompt}\u201d\u2026')

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream_worker():
            from lume.agents.colorist import run_colorist as _gen
            for ev in _gen(
                prompt=_prompt,
                db_path=_db_path,
                project_dir=_project_dir,
                gemini_api_key=_api_key,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, ev)
            loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=_stream_worker, daemon=True)
        thread.start()

        lut_id = None
        while True:
            ev = await queue.get()
            if ev is None:
                break
            async with self:
                self._append_log(ev["agent"], ev["message"], error=ev.get("error", False))
                if ev.get("lut_id"):
                    lut_id = ev["lut_id"]

        async with self:
            self.colorist_running = False
            self._reload_luts_sync()
            if lut_id:
                self.active_tab = "color_lab"
            self._auto_check_todos("colorist")

        if lut_id:
            await self._commit_and_push(
                f'ACTION: Color grading. RESULT: LUT generated for \u201c{_prompt}\u201d.'
            )

    # ── Architect ─────────────────────────────────────────────────────────────

    @rx.event(background=True)
    async def run_architect(self):
        if not self.project_name:
            return

        import asyncio

        async with self:
            self.architect_running = True
            self.last_fcpxml_path = ""
            self.activity_panel_open = True

            # Capture filter state inside the lock
            _db_path      = self.db_path
            _project_name = self.project_name
            _project_dir  = self.project_dir

            # Use filtered clip IDs if any filter is active, otherwise export all
            _filtered_ids = [c.clip_id for c in self.filtered_clips]
            _all_ids      = [c.clip_id for c in self.clips if c.usable]
            _clip_ids     = _filtered_ids if len(_filtered_ids) < len(_all_ids) else None

            if _clip_ids is not None:
                self._append_log(
                    "architect",
                    f"Starting Architect — exporting {len(_clip_ids)} filtered clip(s) (of {len(_all_ids)} total)…"
                )
            else:
                self._append_log("architect", "Starting Architect — generating FCPXML…")

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream_worker():
            from lume.agents.architect import run_architect as _gen
            for ev in _gen(
                db_path=_db_path,
                project_name=_project_name,
                project_dir=_project_dir,
                clip_ids=_clip_ids,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, ev)
            loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=_stream_worker, daemon=True)
        thread.start()

        output_path = ""
        while True:
            ev = await queue.get()
            if ev is None:
                break
            async with self:
                self._append_log(ev["agent"], ev["message"], error=ev.get("error", False))
                if ev.get("output_path"):
                    output_path = ev["output_path"]

        async with self:
            self.architect_running = False
            if output_path:
                self.last_fcpxml_path = output_path
            self._auto_check_todos("architect")

        if output_path:
            import subprocess as sp
            sp.Popen(["open", "-R", output_path])
            await self._commit_and_push(
                f"ACTION: FCPXML export. RESULT: {Path(output_path).name}"
            )

    def reveal_in_finder(self):
        if self.last_fcpxml_path:
            import subprocess as sp
            sp.Popen(["open", "-R", self.last_fcpxml_path])

    # ── Phase 7: Watch Mode ───────────────────────────────────────────────────

    @rx.event(background=True)
    async def start_watcher(self):
        """
        Start watching project directory for FCPXML changes.
        Runs until stop_watcher() is called.
        """
        import asyncio
        import threading

        # Read + guard inside the lock (same pattern as start_source_watcher)
        async with self:
            if not self.project_name or self.watcher_active:
                return
            self.watcher_active = True
            self.activity_panel_open = True
            _project_dir = self.project_dir
            _api_key = get_gemini_api_key()
            self._append_log("watcher", f"Watch mode ON — monitoring {Path(_project_dir).name}/ for FCPXML changes")

        stop_event = threading.Event()
        _watcher_stop_events[_project_dir] = stop_event

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _watch_thread():
            from lume.agents.watcher import run_watcher as _gen
            try:
                for ev in _gen(
                    project_dir=_project_dir,
                    gemini_api_key=_api_key,
                    stop_event=stop_event,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "agent": "watcher", "message": f"Watcher error: {exc}",
                    "commit_message": None, "done": True, "error": True,
                })
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=_watch_thread, daemon=True, name="lume-watcher").start()

        while True:
            ev = await queue.get()
            if ev is None:
                break
            async with self:
                self._append_log(ev["agent"], ev["message"], error=ev.get("error", False))

            commit_msg = ev.get("commit_message")
            if commit_msg:
                await self._commit_and_push(f"WATCH: {commit_msg}")

        async with self:
            self.watcher_active = False
            _watcher_stop_events.pop(_project_dir, None)

    def stop_watcher(self):
        """Signal the watcher thread to stop."""
        stop_ev = _watcher_stop_events.get(self.project_dir)
        if stop_ev:
            stop_ev.set()
        self.watcher_active = False
        self._append_log("watcher", "Watch mode stopping…")

    def toggle_watcher(self):
        """
        Toggle Watch Mode on/off.
        Starting watch is a background task so we yield it as an event;
        stopping is synchronous.
        """
        if self.watcher_active:
            self.stop_watcher()
        else:
            yield LumeState.start_watcher()

    # ── Source Folder Auto-Watch ──────────────────────────────────────────────

    def toggle_source_watcher(self):
        if self.source_watcher_active:
            self.source_watcher_active = False
            self._append_log("librarian", "Auto-watch: stopping…")
        else:
            yield LumeState.start_source_watcher()

    @rx.event(background=True)
    async def start_source_watcher(self):
        """Poll source directory every 15s for new video files. Auto-indexes + scores them."""
        import asyncio
        from pathlib import Path

        async with self:
            if not self.source_dir or self.source_watcher_active:
                return
            self.source_watcher_active = True
            self.activity_panel_open = True
            self._append_log("librarian", f"Auto-watch ON — monitoring for new clips every 15s…")

        _source_dir = self.source_dir
        _project_dir = self.project_dir
        _db_path = self.db_path

        VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.m2ts', '.mxf', '.r3d', '.braw', '.wmv', '.webm'}

        while True:
            async with self:
                if not self.source_watcher_active or not self.db_path:
                    break

            # Scan for new files
            source = Path(_source_dir)
            if not source.exists():
                await asyncio.sleep(15)
                continue

            all_videos = {str(p) for p in source.rglob('*') if p.suffix.lower() in VIDEO_EXTS and p.is_file()}

            from lume.db.models import Clip, get_engine
            from sqlalchemy.orm import Session as _Session
            _engine = get_engine(_db_path)
            with _Session(_engine) as s:
                known = {c.source_path for c in s.query(Clip).all()}

            new_files = all_videos - known
            if not new_files:
                await asyncio.sleep(15)
                continue

            async with self:
                self._append_log("librarian", f"Auto-watch: {len(new_files)} new video(s) detected — indexing…")
                self.librarian_running = True

            import threading
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def _run_lib():
                try:
                    import importlib, lume.agents.librarian as _lib_mod
                    importlib.reload(_lib_mod)
                    for event in _lib_mod.run_librarian(
                        source_dir=_source_dir,
                        project_dir=_project_dir,
                        db_path=_db_path,
                        gemini_api_key=get_gemini_api_key(),
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "agent": "librarian", "message": f"Auto-watch indexing error: {exc}",
                        "clip_id": None, "done": True, "error": True,
                    })
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=_run_lib, daemon=True).start()
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                async with self:
                    self._append_log(ev["agent"], ev["message"], error=ev.get("error", False))

            async with self:
                self.librarian_running = False
                self.librarian_done = True
                self._reload_clips_sync()

            # Run Scout on new clips if Gemini key available
            _api_key = get_gemini_api_key()
            if _api_key:
                async with self:
                    self._append_log("librarian", "Auto-watch: indexing done — starting Scout…")
                    self.scout_running = True

                queue2: asyncio.Queue = asyncio.Queue()

                def _run_scout():
                    try:
                        import importlib, lume.agents.scout as _scout_mod
                        importlib.reload(_scout_mod)
                        for ev in _scout_mod.run_scout(db_path=_db_path, gemini_api_key=_api_key):
                            loop.call_soon_threadsafe(queue2.put_nowait, ev)
                    except Exception as exc:
                        loop.call_soon_threadsafe(queue2.put_nowait, {
                            "agent": "scout", "message": f"Auto-watch scoring error: {exc}",
                            "clip_id": None, "done": True, "error": True,
                        })
                    finally:
                        loop.call_soon_threadsafe(queue2.put_nowait, None)

                threading.Thread(target=_run_scout, daemon=True).start()
                while True:
                    ev2 = await queue2.get()
                    if ev2 is None:
                        break
                    is_scored = bool(ev2.get("clip_id")) and "→" in ev2.get("message", "")
                    async with self:
                        self._append_log(ev2["agent"], ev2["message"], error=ev2.get("error", False))
                        if is_scored:
                            self.scout_scored += 1
                            self._reload_clips_sync()

                async with self:
                    self.scout_running = False
                    self._reload_clips_sync()
                    self._append_log("librarian", "Auto-watch: new clips indexed and scored ✓")
            else:
                async with self:
                    self._append_log("librarian", "Auto-watch: indexing done (set Gemini key to auto-score).")

            await asyncio.sleep(15)

        async with self:
            self.source_watcher_active = False
            self._append_log("librarian", "Auto-watch stopped.")

    # ── Vibe Slider ──────────────────────────────────────────────────────────

    def set_colorist_prompt(self, value: str):
        self.colorist_prompt = value

    def set_vibe_min(self, value: list[float] | float):
        if isinstance(value, list):
            self.vibe_min_score = value[0]
        else:
            self.vibe_min_score = value

    # ── Filter setters ────────────────────────────────────────────────────────

    def set_filter_show(self, value: str):
        """Show row: 'all' | 'people' | 'nature'."""
        self.filter_show = value

    def set_filter_orientation(self, value: str):
        self.filter_orientation = value

    def toggle_filter_favorites(self):
        self.filter_favorites = not self.filter_favorites

    def toggle_filter_high_quality(self):
        self.filter_high_quality = not self.filter_high_quality

    def toggle_favorite(self, clip_id: str):
        """Toggle is_favorite on the Score row for clip_id, then reload clips."""
        if not self.db_path:
            return
        from lume.db.models import Score as _Score
        engine = get_engine(self.db_path)
        with Session(engine) as session:
            row = session.get(_Score, clip_id)
            if row:
                row.is_favorite = 0 if row.is_favorite else 1
                session.commit()
        self._reload_clips_sync()

    def toggle_timeline(self):
        self.timeline_collapsed = not self.timeline_collapsed

    def toggle_scene(self, scene_id: int):
        if scene_id in self.collapsed_scene_ids:
            self.collapsed_scene_ids = [i for i in self.collapsed_scene_ids if i != scene_id]
        else:
            self.collapsed_scene_ids = self.collapsed_scene_ids + [scene_id]

    # ── Edit Diary ────────────────────────────────────────────────────────────

    @rx.event(background=True)
    async def generate_diary(self):
        """
        For each day in grouped_commits, call Gemini to produce a one-sentence
        plain-English summary of what the editor did that day.
        """
        if not self.has_project:
            return

        api_key = get_gemini_api_key()
        if not api_key:
            async with self:
                self._append_log("archivist", "Gemini API key needed for diary summaries.", error=True)
            return

        async with self:
            self.diary_generating = True
            self.active_tab = "summary"
            self._append_log("archivist", "Generating edit diary…")

        _groups = self.grouped_commits  # snapshot before thread

        import asyncio

        loop = asyncio.get_event_loop()
        result_queue: asyncio.Queue = asyncio.Queue()

        def _generate():
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

            entries = []
            for group in _groups:
                if group.summary:          # already generated
                    entries.append((group.date, group.summary))
                    continue
                msgs = "\n".join(f"- {c.message}" for c in group.commits)
                prompt = (
                    f"You are a film editor's assistant writing a daily edit diary entry.\n"
                    f"Given these git commits from {group.label} ({group.date}), "
                    f"write ONE casual sentence (max 120 chars) describing what the editor accomplished.\n"
                    f"Be specific — mention clips, scores, exports, or LUTs if referenced.\n\n"
                    f"Commits:\n{msgs}\n\n"
                    f"Output ONLY the sentence, no quotes, no markdown."
                )
                try:
                    resp = model.generate_content(prompt)
                    summary = resp.text.strip().strip('"').strip("'")[:120]
                except Exception as exc:
                    summary = f"Worked on {len(group.commits)} commit(s)."
                entries.append((group.date, summary))
            loop.call_soon_threadsafe(result_queue.put_nowait, entries)

        await rx.run_in_thread(_generate)
        entries = await result_queue.get()

        async with self:
            self.diary_entries = [
                DaySummary(date=date, label="", commits=[], summary=summary)
                for date, summary in entries
            ]
            self.diary_generating = False
            self._append_log("archivist", f"Diary generated for {len(entries)} day(s).")

    # ── Smart LUT ─────────────────────────────────────────────────────────────

    @rx.event(background=True)
    async def generate_smart_lut(self):
        """
        Analyze hero frames from top-scored / favorite clips with Gemini and
        auto-fill the colorist prompt with a professional color grade brief.
        """
        if not self.has_project:
            return

        api_key = get_gemini_api_key()
        if not api_key:
            async with self:
                self._append_log("colorist", "Gemini API key needed for Smart LUT.", error=True)
            return

        _db_path = self.db_path

        async with self:
            self.smart_lut_running = True
            self.active_tab = "color_lab"
            self._append_log("colorist", "Smart LUT: analysing your footage…")

        import asyncio, base64

        loop = asyncio.get_event_loop()
        result_queue: asyncio.Queue = asyncio.Queue()

        def _analyse():
            upload_root = Path.cwd() / "uploaded_files"
            engine = get_engine(_db_path)

            # Gather up to 6 hero frames from favorites or highest-scored clips
            with Session(engine) as session:
                from lume.db.models import Score as _Score, HeroFrame as _HF
                # Prefer favorites, then top scores
                fav_ids = [
                    r.clip_id for r in
                    session.query(_Score)
                    .filter(_Score.is_favorite == 1)
                    .order_by(_Score.score.desc())
                    .limit(6).all()
                ]
                if len(fav_ids) < 3:
                    top_ids = [
                        r.clip_id for r in
                        session.query(_Score)
                        .order_by(_Score.score.desc())
                        .limit(6).all()
                    ]
                    fav_ids = list(dict.fromkeys(fav_ids + top_ids))[:6]

                frame_keys = []
                for clip_id in fav_ids:
                    hf = session.query(_HF).filter_by(clip_id=clip_id).first()
                    if hf:
                        frame_keys.append(hf.frame_path)

            if not frame_keys:
                loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    ("", "No scored clips found — run Scout first.")
                )
                return

            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

            parts = [
                "You are a professional colorist. Analyze these video frames and write a "
                "1-2 sentence color grade brief that would enhance the visual storytelling. "
                "Be specific about temperature (warm/cool), contrast, shadow treatment, "
                "highlight rolloff, and emotional mood. Reference a real film look if fitting.\n"
                "Output ONLY the brief — no markdown, no labels, no explanation."
            ]
            loaded = 0
            for key in frame_keys[:6]:
                path = upload_root / key
                if path.exists():
                    try:
                        data = base64.b64encode(path.read_bytes()).decode()
                        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": data}})
                        loaded += 1
                    except Exception:
                        pass

            if loaded == 0:
                loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    ("", "Could not load hero frames — try re-running Librarian.")
                )
                return

            try:
                resp = model.generate_content(parts)
                brief = resp.text.strip().strip('"').strip("'")
            except Exception as exc:
                brief = ""
                loop.call_soon_threadsafe(
                    result_queue.put_nowait, ("", f"Gemini error: {exc}")
                )
                return

            loop.call_soon_threadsafe(result_queue.put_nowait, (brief, ""))

        await rx.run_in_thread(_analyse)
        brief, err = await result_queue.get()

        async with self:
            self.smart_lut_running = False
            if err:
                self._append_log("colorist", f"Smart LUT failed: {err}", error=True)
            else:
                self.colorist_prompt = brief
                self._append_log("colorist", f"Smart LUT brief ready: \"{brief[:80]}…\"")

    # ── Best Clips Story ──────────────────────────────────────────────────────

    @rx.event(background=True)
    async def generate_best_clips_story(self):
        """
        Sends the best clips metadata to Gemini and generates a 2-3 sentence
        narrative explaining why they are the hero clips.
        """
        if not self.best_clips_story_enabled:
            return

        _api_key = get_gemini_api_key()
        if not _api_key:
            async with self:
                self._append_log("colorist",
                                 "Gemini API key needed for Best Clips Story.", error=True)
            return

        _best = list(self.best_clips)

        async with self:
            self.best_clips_story_running = True
            self._append_log("colorist", "Generating best clips story…")

        import asyncio

        result_queue: asyncio.Queue = asyncio.Queue()

        def _run():
            try:
                import google.generativeai as genai

                genai.configure(api_key=_api_key)
                model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

                clip_descriptions = "\n".join(
                    f"- {c.filename}: score {c.score:.1f}, orientation {c.orientation}, "
                    f"tags: {', '.join(c.tags)}, has_people: {c.has_people == 1}"
                    for c in _best
                )

                prompt = (
                    "You are a film editor's assistant. Based on these standout clips, "
                    "write a 2–3 sentence narrative (max 90 words) explaining COHESIVELY "
                    "why they are the hero clips — be specific about visual qualities, "
                    "themes, and what makes them special together as a set. "
                    "Write in second person ('Your top clips…'). Do not list the clips individually.\n\n"
                    f"Clips:\n{clip_descriptions}"
                )

                resp = model.generate_content(prompt)
                result_queue.put_nowait((resp.text.strip(), None))
            except Exception as exc:
                result_queue.put_nowait(("", str(exc)))

        await rx.run_in_thread(_run)
        text, err = await result_queue.get()

        async with self:
            self.best_clips_story_running = False
            if err:
                self._append_log("colorist", f"Best clips story failed: {err}", error=True)
            else:
                self.best_clips_story = text
                self._append_log("colorist", "Best clips story ready.")

    # ── Creative Suggestions ──────────────────────────────────────────────────

    @rx.event(background=True)
    async def generate_creative_suggestions(self):
        """
        Analyzes the clip collection's tags, scores, orientations, and hero
        frames to suggest fonts, transitions, edit pacing, and color direction.
        Result is stored in self.creative_suggestions as a markdown-ish string.
        """
        if not self.creative_suggestions_enabled:
            return

        _api_key = get_gemini_api_key()
        if not _api_key:
            async with self:
                self._append_log("colorist",
                                 "Gemini API key needed for Creative Suggestions.", error=True)
            return

        _clips = list(self.clips)

        async with self:
            self.creative_suggestions_running = True
            self._append_log("colorist", "Generating creative suggestions…")

        import asyncio, queue as _queue

        result_queue: asyncio.Queue = asyncio.Queue()

        def _run():
            try:
                import google.generativeai as genai
                from pathlib import Path
                import base64, json

                genai.configure(api_key=_api_key)
                model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

                # Build a text summary of the clip collection
                scored = sorted(
                    [c for c in _clips if c.score >= 0 and c.usable],
                    key=lambda c: c.score, reverse=True,
                )
                all_tags: list[str] = []
                for c in _clips:
                    all_tags.extend(c.tags)
                from collections import Counter
                tag_freq = Counter(all_tags).most_common(10)
                has_people_count = sum(1 for c in _clips if c.has_people == 1)
                portrait_count = sum(1 for c in _clips if c.orientation == "portrait")
                landscape_count = sum(1 for c in _clips if c.orientation == "landscape")
                avg_score = (
                    sum(c.score for c in scored) / len(scored) if scored else 0.0
                )

                clip_summary = (
                    f"Total clips: {len(_clips)}, "
                    f"avg score: {avg_score:.1f}, "
                    f"landscape: {landscape_count}, portrait: {portrait_count}, "
                    f"clips with people: {has_people_count}. "
                    f"Top tags: {', '.join(t for t, _ in tag_freq)}."
                )

                prompt = (
                    "You are a creative director advising a video editor.\n"
                    "Based on this footage library, give concise creative suggestions in 4 sections:\n\n"
                    "1. **Font Pairing** — 2 font names (headline + body) that match the footage mood.\n"
                    "2. **Transition Style** — Recommended edit rhythm (hard cuts, dissolves, etc.) with 1-sentence reason.\n"
                    "3. **Edit Pacing** — Tight/loose cut rhythm advice based on the content type.\n"
                    "4. **Color Direction** — One-sentence color grade mood suggestion.\n\n"
                    f"Footage summary: {clip_summary}\n\n"
                    "Respond in plain text with the 4 numbered sections above. No markdown code blocks. Be concise (max 60 words per section)."
                )

                resp = model.generate_content(prompt)
                result_queue.put_nowait((resp.text.strip(), None))
            except Exception as exc:
                result_queue.put_nowait(("", str(exc)))

        await rx.run_in_thread(_run)
        text, err = await result_queue.get()

        async with self:
            self.creative_suggestions_running = False
            if err:
                self._append_log("colorist", f"Creative suggestions failed: {err}", error=True)
            else:
                self.creative_suggestions = text
                self._append_log("colorist", "Creative suggestions ready.")

    # ── Audio Lab ─────────────────────────────────────────────────────────────

    def set_freesound_api_key_input(self, value: str):
        self.freesound_api_key_input = value

    @rx.event(background=True)
    async def run_audio_agent(self):
        if not self.audio_agent_enabled:
            return

        from lume.config import get_freesound_api_key as _get_fs_key
        _gemini_key = get_gemini_api_key() or ""
        _freesound_key = self.freesound_api_key_input or _get_fs_key() or ""

        _db_path = self.db_path

        async with self:
            self.audio_agent_running = True
            self.activity_panel_open = True
            self._append_log("librarian", "Audio Agent starting…")

        import asyncio
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _worker():
            from lume.agents.audio_agent import run_audio_agent as _gen
            for ev in _gen(
                db_path=_db_path,
                gemini_api_key=_gemini_key,
                freesound_api_key=_freesound_key,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, ev)
            loop.call_soon_threadsafe(queue.put_nowait, None)

        import threading
        threading.Thread(target=_worker, daemon=True).start()

        while True:
            ev = await queue.get()
            if ev is None:
                break
            async with self:
                self._append_log(
                    ev["agent"], ev["message"],
                    error=ev.get("error", False),
                )
                if ev.get("clip_id"):
                    self._reload_clips_sync()

        async with self:
            self.audio_agent_running = False
            self._reload_clips_sync()
            self._auto_check_todos("audio")
            _clip_count = len(self.clips)

        await self._commit_and_push(
            f"ACTION: Audio Agent. RESULT: Royalty-free audio matched for {_clip_count} clip(s)."
        )

    def assign_audio(self, track_id: int):
        """Toggle assigned flag on an AudioMatch row."""
        if not self.db_path:
            return
        engine = get_engine(self.db_path)
        with Session(engine) as session:
            row = session.get(AudioMatch, track_id)
            if row:
                row.assigned = 0 if row.assigned else 1
                session.commit()
        self._reload_clips_sync()

    # ── Projects panel ────────────────────────────────────────────────────────

    def open_projects_panel(self):
        self._load_all_projects_sync()
        self.show_projects_panel = True

    def close_projects_panel(self):
        self.show_projects_panel = False

    def _load_all_projects_sync(self):
        from lume.config import list_projects
        from lume.db.models import Score as ScoreModel
        projects = list_projects()
        entries: list[ProjectEntry] = []
        for p in projects:
            pdir = Path(p["path"])
            db = pdir / "lume.db"
            clip_count = 0
            fav_count = 0
            last_commit_at = ""
            push_pending = 0
            if db.exists():
                try:
                    eng = get_engine(str(db))
                    with Session(eng) as s:
                        clip_count = s.query(Clip).count()
                        fav_count = s.query(ScoreModel).filter(ScoreModel.is_favorite == 1).count()
                        last = s.query(GitCommit).order_by(GitCommit.id.desc()).first()
                        if last:
                            last_commit_at = (last.created_at or "")[:10]
                        push_pending = s.query(GitCommit).filter(GitCommit.pushed == 0).count()
                except Exception:
                    pass
            entries.append(ProjectEntry(
                name=p["name"],
                path=p["path"],
                remote=p.get("remote", ""),
                active=bool(p.get("active")),
                clip_count=clip_count,
                fav_count=fav_count,
                push_pending=push_pending,
                last_commit_at=last_commit_at,
            ))
        self.all_projects = entries

    def switch_project(self, name: str):
        """Switch to a different project and reload state."""
        from lume.config import set_active_project
        set_active_project(name)
        self.show_projects_panel = False
        # Reset agent/filter state
        self.clips = []
        self.commits = []
        self.lut_history = []
        self.log_lines = []
        self.last_fcpxml_path = ""
        self.librarian_done = False
        self.watcher_active = False
        self.source_watcher_active = False
        self.filter_show = "all"
        self.filter_people = "all"
        self.filter_orientation = "all"
        self.filter_favorites = False
        self.filter_high_quality = False
        self.diary_entries = []
        self.creative_suggestions = ""
        self.best_clips_story = ""
        self.scenes = []
        self.collapsed_scene_ids = []
        self.audio_groups = []
        self.group_by_content = False
        self.collapsed_content_groups = []
        self.todo_items = []
        self.todo_input = ""
        self.load_active_project()

    # ── Tab switching ────────────────────────────────────────────────────────

    def set_tab(self, tab: str):
        self.active_tab = tab

    # ── Video preview ─────────────────────────────────────────────────────────

    def select_clip(self, clip_id: str):
        """Select a clip — loads its hero frames from DB for the keyframe strip."""
        self.selected_clip_id = clip_id
        # Find name from clips list
        for card in self.clips:
            if card.clip_id == clip_id:
                self.selected_clip_name = card.filename
                break
        # Load all hero frames for this clip from DB
        if not self.db_path:
            return
        try:
            engine = get_engine(self.db_path)
            with Session(engine) as session:
                frames = (
                    session.query(HeroFrame)
                    .filter_by(clip_id=clip_id)
                    .order_by(HeroFrame.timestamp_seconds)
                    .all()
                )
                # Take up to 5 evenly-spaced frames
                keys = [f.frame_path for f in frames]
                if len(keys) > 5:
                    step = len(keys) / 5
                    keys = [keys[int(i * step)] for i in range(5)]
                self.selected_clip_frames = keys
        except Exception:
            self.selected_clip_frames = []

    # ── Internal helpers (not event handlers) ────────────────────────────────

    def _init_default_todos(self):
        """Ensure default AI-suggested todos are present, with done state inferred from DB."""
        # Query DB to determine which agents have already done work
        completed: set[str] = set()
        if self.db_path:
            try:
                from lume.db.models import Clip, Score as ScoreModel, Lut, AudioMatch, get_engine
                from sqlalchemy.orm import Session as _S
                engine = get_engine(self.db_path)
                with _S(engine) as s:
                    if s.query(Clip).filter(Clip.usable == 1).count() > 0:
                        completed.add("librarian")
                    if s.query(ScoreModel).count() > 0:
                        completed.add("scout")
                    if s.query(Lut).count() > 0:
                        completed.add("colorist")
                    if s.query(AudioMatch).filter(AudioMatch.assigned == 1).count() > 0:
                        completed.add("audio")
                    # architect: check if any FCPXML export exists on disk
                    from pathlib import Path as _P
                    exports_dir = _P(self.project_dir) / "exports"
                    if exports_dir.exists() and any(exports_dir.glob("*.fcpxml")):
                        completed.add("architect")
            except Exception:
                pass

        existing_ids = {item.item_id for item in self.todo_items}
        to_add = []
        for t in _DEFAULT_AI_TODOS:
            if t.item_id not in existing_ids:
                to_add.append(TodoItem(
                    item_id=t.item_id, text=t.text,
                    done=(t.agent_trigger in completed),
                    ai_generated=t.ai_generated,
                    agent_trigger=t.agent_trigger,
                ))
        if to_add:
            self.todo_items = to_add + list(self.todo_items)

    def _auto_check_todos(self, agent: str):
        """Mark all todo items whose agent_trigger matches *agent* as done."""
        updated = []
        for item in self.todo_items:
            if item.agent_trigger == agent and not item.done:
                updated.append(TodoItem(
                    item_id=item.item_id, text=item.text,
                    done=True, ai_generated=item.ai_generated,
                    agent_trigger=item.agent_trigger,
                ))
            else:
                updated.append(item)
        self.todo_items = updated

    def _append_log(self, agent: str, message: str, error: bool = False):
        self.log_lines = self.log_lines + [
            LogLine(agent=agent, message=message, error=error, ts=_now())
        ]
        # Keep last 500 lines to avoid unbounded growth
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]

    def _reload_clips_sync(self):
        if not self.db_path:
            return
        engine = get_engine(self.db_path)
        cards: list[ClipCard] = []
        with Session(engine) as session:
            clips = session.query(Clip).all()
            for clip in clips:
                score_row = session.query(Score).filter_by(clip_id=clip.id).first()
                tags = [t.tag for t in session.query(Tag).filter_by(clip_id=clip.id).all()]
                # Best hero frame = first one
                hero = session.query(HeroFrame).filter_by(clip_id=clip.id).first()
                # Store the upload-relative key (e.g. lume_frames/<id>/frame.jpg).
                # The component calls rx.get_upload_url(key) to get the correct
                # backend URL — this works in both dev and prod.
                hero_path = hero.frame_path if hero else ""
                cards.append(ClipCard(
                    clip_id=clip.id,
                    filename=Path(clip.source_path).name,
                    duration=clip.duration_seconds or 0.0,
                    score=score_row.score if score_row and score_row.score is not None else -1.0,
                    stability=score_row.stability if score_row and score_row.stability is not None else -1.0,
                    focus=score_row.focus if score_row and score_row.focus is not None else -1.0,
                    lighting=score_row.lighting if score_row and score_row.lighting is not None else -1.0,
                    hero_frame=hero_path,
                    proxy_path=clip.proxy_path or "",
                    tags=tags,
                    usable=bool(clip.usable),
                    orientation=clip.orientation or "landscape",
                    has_people=clip.has_people if clip.has_people is not None else -1,
                    is_favorite=bool(score_row.is_favorite) if score_row else False,
                    scene_id=clip.scene_id or -1,
                ))
        self.clips = cards

        # Reload scenes
        scene_list: list[SceneEntry] = []
        with Session(engine) as session:
            for s in session.query(Scene).order_by(Scene.shoot_date).all():
                scene_list.append(SceneEntry(
                    scene_id=s.id,
                    name=s.name or f"Scene {s.id}",
                    description=s.description or "",
                    shoot_date=s.shoot_date or "",
                    clip_count=s.clip_count or 0,
                ))
        self.scenes = scene_list

        # Reload audio groups
        audio_list: list[AudioGroup] = []
        with Session(engine) as session:
            for clip in session.query(Clip).filter(Clip.audio_keywords != None).all():
                hero = session.query(HeroFrame).filter_by(clip_id=clip.id).first()
                matches = session.query(AudioMatch).filter_by(clip_id=clip.id).all()
                tracks = [
                    AudioTrack(
                        track_id=m.id,
                        clip_id=clip.id,
                        clip_name=Path(clip.source_path).name,
                        name=m.name or "",
                        preview_url=m.preview_url or "",
                        duration=m.duration or 0.0,
                        assigned=bool(m.assigned),
                        local_path=m.local_path or "",
                    )
                    for m in matches
                ]
                audio_list.append(AudioGroup(
                    clip_id=clip.id,
                    clip_name=Path(clip.source_path).name,
                    hero_frame=hero.frame_path if hero else "",
                    keywords=clip.audio_keywords or "",
                    tracks=tracks,
                ))
        self.audio_groups = audio_list

    def _reload_luts_sync(self):
        if not self.db_path:
            return
        engine = get_engine(self.db_path)
        entries: list[LutEntry] = []
        with Session(engine) as session:
            rows = session.query(Lut).order_by(Lut.id.desc()).limit(20).all()
            for row in rows:
                entries.append(LutEntry(
                    lut_id=row.id,
                    prompt=row.prompt,
                    before_frame=row.before_frame_path or "",
                    after_frame=row.after_frame_path or "",
                    created_at=row.created_at or "",
                ))
        self.lut_history = entries

    def _reload_commits_sync(self):
        if not self.db_path:
            return
        engine = get_engine(self.db_path)
        entries: list[CommitEntry] = []
        with Session(engine) as session:
            rows = session.query(GitCommit).order_by(GitCommit.id.desc()).limit(50).all()
            for row in rows:
                entries.append(CommitEntry(
                    sha=row.sha or "",
                    message=row.message,
                    pushed=bool(row.pushed),
                    created_at=row.created_at or "",
                ))
        self.commits = entries

    def _migrate_hero_frame_paths(self):
        """
        One-time migration: absolute frame paths stored by earlier Librarian runs
        are converted to upload-relative keys (lume_frames/<clip_id>/file.jpg).
        Idempotent — paths that are already relative keys are left untouched.
        """
        if not self.db_path:
            return
        upload_root = (Path.cwd() / "uploaded_files").resolve()
        frames_root = upload_root / "lume_frames"
        engine = get_engine(self.db_path)
        with Session(engine) as session:
            rows = session.query(HeroFrame).all()
            changed = 0
            for row in rows:
                p = Path(row.frame_path)
                # Already a relative key — skip
                if not p.is_absolute():
                    continue
                # Absolute path: copy frame to upload dir if not already there
                clip_id = row.clip_id
                dest_dir = frames_root / clip_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / p.name
                if not dest.exists() and p.exists():
                    import shutil
                    shutil.copy2(str(p), str(dest))
                if dest.exists():
                    row.frame_path = str(dest.relative_to(upload_root))
                    changed += 1
            if changed:
                session.commit()

    async def _reload_commits(self):
        # Must wrap in context manager — this can be called from a background task
        # where self is a StateProxy and writes outside async with self raise ImmutableStateError.
        async with self:
            self._reload_commits_sync()

    async def _commit_and_push(self, message: str):
        if not self.project_dir or not self.db_path:
            return
        pat = get_github_pat()
        db_path = self.db_path
        project_dir = self.project_dir
        github_remote = self.github_remote
        engine = get_engine(db_path)
        try:
            # Force WAL checkpoint so all DB changes land in lume.db before
            # git stages it — without this, SQLite WAL mode keeps changes in
            # lume.db-wal and git sees lume.db as unchanged.
            try:
                with Session(engine) as ckpt:
                    ckpt.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            except Exception as wal_err:
                # Non-fatal — log and continue. DB may need manual recovery.
                logger.warning("WAL checkpoint skipped: %s", wal_err)

            # Use persistent singleton Archivist — push worker runs for the
            # entire process lifetime, queue never reset between commits.
            arch = get_or_create_archivist(
                project_dir=project_dir,
                db_engine=engine,
                remote_url=github_remote,
                github_pat=pat,
            )
            sha = arch.commit(message)
            # Give the push worker a moment to complete before reading status
            import asyncio
            await asyncio.sleep(2)
            status = arch.push_status
            async with self:
                self.push_status_state = status["state"]
                self.push_status_label = status["label"]
                self.push_pending_count = status["pending"]
                self._reload_commits_sync()
                if sha:
                    self._append_log("archivist", f"Committed: {message}")
                else:
                    self._append_log("archivist", f"Nothing to commit for: {message}")
        except Exception as exc:
            async with self:
                self._append_log("archivist", f"Commit failed: {exc}", error=True)

    # ── Phase 6: LUT assignment ───────────────────────────────────────────────

    @rx.event(background=True)
    async def assign_lut_to_clips(self, lut_id: int):
        """
        Assign *lut_id* to all usable clips, replacing any existing assignments.
        The Architect will apply this LUT on the next FCPXML export.
        """
        if not self.db_path:
            return

        _db_path = self.db_path
        _lut_id = lut_id

        async with self:
            self._append_log("colorist", f"Assigning LUT #{_lut_id} to all clips…")

        def _do_assign():
            from lume.db.models import ClipLutAssignment as _CLA
            eng = get_engine(_db_path)
            with Session(eng) as session:
                clips = session.query(Clip).filter(Clip.usable == 1).all()
                session.query(_CLA).delete()
                for clip in clips:
                    session.add(_CLA(clip_id=clip.id, lut_id=_lut_id))
                session.commit()
                return len(clips)

        count = await rx.run_in_thread(_do_assign)

        async with self:
            self._append_log(
                "colorist",
                f"LUT #{_lut_id} assigned to {count} clip(s). "
                "Architect will apply it on the next FCPXML export.",
            )

        await self._commit_and_push(
            f"ACTION: LUT assignment. RESULT: LUT #{_lut_id} assigned to {count} clip(s)."
        )

    # ── Phase 6: push status refresh ─────────────────────────────────────────

    def refresh_push_status(self):
        """
        Poll the persistent Archivist for current push status and refresh
        the commit list.  Called by the Refresh button in the Version Timeline.
        """
        if not self.project_dir:
            return
        key = str(Path(self.project_dir).resolve())
        arch = _archivist_registry.get(key)
        if arch is None:
            return
        status = arch.push_status
        self.push_status_state = status["state"]
        self.push_status_label = status["label"]
        self.push_pending_count = status["pending"]
        self._reload_commits_sync()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")
