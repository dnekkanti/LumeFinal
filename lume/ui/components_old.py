"""
Reusable Lume UI components — redesigned for Phase 7.

Changes vs Phase 6:
  - header():         project breadcrumb/switcher, grouped agent pill, watch toggle
  - library_panel():  three filter rows (people / orientation / status) + vibe slider
  - clip_card():      orientation badge, people badge, taller portrait thumbs
  - version_timeline(): date-grouped commits with type icons
  - projects_panel(): slide-in overlay listing all projects
  - export_banner():  warmer gradient styling
"""

from __future__ import annotations

from datetime import datetime, timezone

import reflex as rx

from lume.state import (
    AudioGroup, AudioTrack, ClipCard, CommitEntry, DaySummary,
    LogLine, LutEntry, ProjectEntry, SceneEntry, LumeState,
)
from lume.ui.theme import (
    AMBER, BLUE, CORAL, GREEN, SCORE_AMBER, SCORE_CORAL, SCORE_GREEN, TEAL,
)

_PURPLE  = "#8B5CF6"
_CYAN    = "#06B6D4"
_PINK    = "#EC4899"
_ORANGE  = "#F97316"
_BLUE    = "#3B82F6"
_GREEN   = "#22C55E"
_AMBER   = "#F59E0B"
_RED     = "#EF4444"
_BG      = "#F9F9FB"
_PANEL   = "#FFFFFF"
_ACTIVE  = "#F3F4F6"
_BORDER  = "#E5E7EB"
_TEXT1   = "#111827"
_TEXT2   = "#6B7280"
_TEXT3   = "#9CA3AF"
GRAY_900 = "#111827"
GRAY_700 = "#6B7280"
GRAY_400 = "#9CA3AF"
GRAY_200 = "#E5E7EB"
GRAY_100 = "#FFFFFF"
GRAY_50  = "#F9F9FB"
_G50     = "#F9F9FB"
_G600    = "#6B7280"
_INDIGO  = "#3B82F6"
_SHADOW_SM = "0 1px 3px rgba(0,0,0,0.40), 0 1px 2px rgba(0,0,0,0.30)"
_SHADOW_MD = "0 4px 14px rgba(0,0,0,0.50), 0 2px 4px rgba(0,0,0,0.35)"

# Gradient shorthands
_GRAD_PURPLE_PINK = "#8B5CF6"
_GRAD_BG          = "#F9F9FB"
WHITE = "#FFFFFF"   # pure white — used only for text/icons on colored backgrounds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_color(score: rx.Var) -> rx.Var:
    return rx.cond(
        score < 0, GRAY_400,
        rx.cond(score >= 8.5, SCORE_GREEN, rx.cond(score >= 6.0, SCORE_AMBER, SCORE_CORAL)),
    )

def _score_label(score: rx.Var) -> rx.Var:
    return rx.cond(score < 0, "—", score.to_string())


# ── Agent badge (Thought Stream) ──────────────────────────────────────────────

def agent_badge(agent: rx.Var | str) -> rx.Component:
    color = rx.match(
        agent,
        ("librarian", TEAL), ("scout", _PURPLE), ("colorist", AMBER),
        ("architect", CORAL), ("archivist", BLUE), ("watcher", GREEN),
        GRAY_400,
    )
    label = rx.match(
        agent,
        ("librarian", "Librarian"), ("scout", "Scout"), ("colorist", "Colorist"),
        ("architect", "Architect"), ("archivist", "Archivist"), ("watcher", "Watcher"),
        agent,
    )
    return rx.box(
        rx.text(label, size="1", weight="bold", color=WHITE),
        padding="1px 8px", border_radius="999px", background=color,
        display="inline-flex", align_items="center", flex_shrink="0",
    )


# ── Log line ──────────────────────────────────────────────────────────────────

def log_line_item(line: LogLine) -> rx.Component:
    return rx.hstack(
        rx.text(line.ts, size="1", color=GRAY_400, font_family="monospace",
                flex_shrink="0"),
        agent_badge(line.agent),
        rx.text(line.message, size="1", font_family="monospace",
                color=rx.cond(line.error, CORAL, GRAY_700), flex_wrap="wrap"),
        spacing="2", align="start", width="100%",
        padding_y="3px",
        border_bottom=f"1px solid {GRAY_100}",
    )


# ── Thought Stream ────────────────────────────────────────────────────────────

def thought_stream() -> rx.Component:
    return rx.box(
        rx.cond(
            LumeState.log_lines.length() == 0,
            rx.center(
                rx.vstack(
                    rx.icon("activity", size=32, color=GRAY_200),
                    rx.text("Agent logs will appear here.", color=GRAY_400, size="2"),
                    spacing="2", align="center",
                ),
                height="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(LumeState.log_lines, log_line_item),
                    spacing="0", width="100%", align="start",
                ),
                height="100%", width="100%",
            ),
        ),
        height="100%", width="100%", padding="16px",
        background=_PANEL, border_radius="8px",
    )


# ── Clip card ─────────────────────────────────────────────────────────────────

def clip_card(clip: ClipCard) -> rx.Component:
    score_col = _score_color(clip.score)
    score_lbl = _score_label(clip.score)

    # Portrait clips get a taller thumbnail
    thumb_height = rx.cond(clip.orientation == "portrait", "100px", "80px")

    thumbnail = rx.cond(
        clip.hero_frame != "",
        rx.image(
            src=rx.get_upload_url(clip.hero_frame),
            width="100%", aspect_ratio="16/9", object_fit="cover",
            border_radius="12px 12px 0 0",
        ),
        rx.box(
            rx.icon("film", size=22, color=GRAY_400),
            width="100%", aspect_ratio="16/9", background=GRAY_100,
            border_radius="12px 12px 0 0",
            display="flex", align_items="center", justify_content="center",
        ),
    )

    # Score pill — top-right corner
    score_pill = rx.cond(
        clip.score >= 0,
        rx.box(
            rx.text(score_lbl, font_size="13px", font_weight="700", color=WHITE),
            position="absolute", top="6px", right="6px",
            background=score_col, padding="3px 9px",
            border_radius="999px",
        ),
        rx.fragment(),
    )

    # Orientation badge — bottom-left
    orient_label = rx.cond(
        clip.orientation == "portrait", "▮ 9:16",
        rx.cond(clip.orientation == "square", "■ 1:1", "⬛ 16:9")
    )
    orient_badge = rx.box(
        rx.text(orient_label, size="1", color="rgba(255,255,255,0.85)",
                weight="bold", font_size="9px"),
        position="absolute", bottom="5px", left="5px",
        background="rgba(0,0,0,0.50)",
        padding="1px 5px", border_radius="4px",
    )

    # People badge — bottom-right (only when detected)
    people_badge = rx.cond(
        clip.has_people == 1,
        rx.box(
            rx.text("👤", font_size="10px"),
            position="absolute", bottom="5px", right="5px",
            background=f"rgba(16,185,129,0.22)",
            border=f"1px solid rgba(16,185,129,0.45)",
            padding="1px 4px", border_radius="4px",
        ),
        rx.fragment(),
    )

    thumb_area = rx.box(
        thumbnail,
        score_pill,
        orient_badge,
        people_badge,
        position="relative",
        width="100%",
    )

    return rx.box(
        thumb_area,
        rx.box(
            rx.hstack(
                rx.text(
                    clip.filename, size="2", weight="medium", color=GRAY_900,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
                    flex="1",
                ),
                spacing="1", width="100%", align="center",
            ),
            rx.hstack(
                # Favorite toggle button — always visible, filled when fav
                rx.button(
                    rx.cond(
                        clip.is_favorite,
                        rx.text("★ Fav", size="1", color=GREEN, weight="bold"),
                        rx.text("☆", size="1", color=GRAY_400),
                    ),
                    on_click=LumeState.toggle_favorite(clip.clip_id),
                    background=rx.cond(
                        clip.is_favorite, "#1A2A1A", "transparent",
                    ),
                    border=rx.cond(
                        clip.is_favorite,
                        f"1px solid {GREEN}50",
                        f"1px solid {GRAY_200}",
                    ),
                    border_radius="999px", padding="1px 7px", height="auto",
                    cursor="pointer",
                    _hover={"background": "#1A2A1A", "border_color": GREEN},
                    transition="all 0.12s",
                    flex_shrink="0",
                ),
                # Duration
                rx.box(
                    rx.text(
                        rx.cond(
                            clip.duration > 0,
                            rx.cond(
                                clip.duration >= 60,
                                (clip.duration / 60).to_string() + "m",
                                clip.duration.to_string() + "s",
                            ),
                            "—",
                        ),
                        size="2", color=GRAY_400,
                    ),
                    background=GRAY_100, padding="1px 6px", border_radius="999px",
                ),
                # Tags (first 2)
                rx.foreach(
                    clip.tags,
                    lambda tag: rx.box(
                        rx.text(tag, size="1", color=_PURPLE),
                        background=f"{_PURPLE}20", padding="1px 6px", border_radius="999px",
                    ),
                ),
                flex_wrap="wrap", spacing="1", padding_top="4px",
            ),
            rx.cond(
                ~clip.usable,
                rx.text("✕ Culled", size="1", color=CORAL, weight="medium"),
                rx.fragment(),
            ),
            padding="10px 12px 12px",
        ),
        background=rx.cond(clip.usable, _PANEL, "#FEF2F2"),
        border="1px solid rgba(0,0,0,0.06)",
        border_radius="10px", overflow="hidden",
        cursor="default",
        _hover={"border_color": "#D1D5DB", "transform": "translateY(-1px)"},
        transition="all 0.18s ease",
    )


# ── Filter chip ───────────────────────────────────────────────────────────────

def _filter_chip(label: str, value: str, current: rx.Var,
                 on_click, active_color: str) -> rx.Component:
    is_active = current == value
    return rx.button(
        label,
        on_click=on_click,
        background=rx.cond(is_active, f"{active_color}30", _PANEL),
        color=rx.cond(is_active, active_color, GRAY_400),
        border=rx.cond(
            is_active,
            f"1.5px solid {active_color}",
            f"1.5px solid {GRAY_200}",
        ),
        border_radius="999px",
        padding="5px 12px",
        font_size="13px",
        font_weight="600",
        cursor="pointer",
        height="30px",
        _hover={"border_color": active_color, "color": active_color},
        transition="all 0.1s",
    )

def _toggle_chip(label: str, is_active: rx.Var,
                 on_click, active_color: str) -> rx.Component:
    return rx.button(
        label,
        on_click=on_click,
        background=rx.cond(is_active, f"{active_color}30", _PANEL),
        color=rx.cond(is_active, active_color, GRAY_400),
        border=rx.cond(
            is_active,
            f"1.5px solid {active_color}",
            f"1.5px solid {GRAY_200}",
        ),
        border_radius="999px",
        padding="5px 12px",
        font_size="13px",
        font_weight="600",
        cursor="pointer",
        height="30px",
        _hover={"border_color": active_color, "color": active_color},
        transition="all 0.1s",
    )


_SCENE_COLORS = [TEAL, _PURPLE, AMBER, CORAL, BLUE, GREEN]


def _scene_clips(scene_id: int) -> rx.Component:
    """Grid of filtered clips belonging to this scene."""
    scene_clips = rx.Var.create([
        c for c in LumeState.filtered_clips
        if c.scene_id == scene_id  # type: ignore[attr-defined]
    ])
    return rx.grid(
        rx.foreach(
            LumeState.filtered_clips,
            lambda c: rx.cond(
                c.scene_id == scene_id,
                clip_card(c),
                rx.fragment(),
            ),
        ),
        columns="2", spacing="2", width="100%",
        padding="4px 0",
    )


def _scene_group(scene: SceneEntry) -> rx.Component:
    color = TEAL  # single color is fine — cycles would need index which foreach doesn't expose
    is_collapsed = LumeState.collapsed_scene_ids.contains(scene.scene_id)

    return rx.vstack(
        # Scene header
        rx.hstack(
            rx.box(
                width="10px", height="10px", border_radius="50%",
                background=_GRAD_PURPLE_PINK, flex_shrink="0",
            ),
            rx.vstack(
                rx.text(scene.name, size="3", weight="bold", color=GRAY_900,
                        overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
                rx.cond(
                    scene.description != "",
                    rx.text(scene.description, size="1", color=GRAY_400,
                            overflow="hidden", text_overflow="ellipsis",
                            white_space="nowrap"),
                    rx.fragment(),
                ),
                spacing="0", align="start", flex="1", min_width="0",
            ),
            rx.box(
                rx.text(scene.clip_count.to_string() + " clips",
                        size="1", weight="bold", color=_G600),
                background=GRAY_100, border_radius="999px", padding="2px 8px",
                flex_shrink="0",
            ),
            rx.button(
                rx.cond(is_collapsed,
                        rx.icon("chevron-right", size=14),
                        rx.icon("chevron-down", size=14)),
                on_click=LumeState.toggle_scene(scene.scene_id),
                background="transparent", border="none", color=GRAY_400,
                cursor="pointer", padding="2px 4px", border_radius="6px",
                _hover={"color": _PURPLE, "background": GRAY_100},
            ),
            width="100%", align="center", spacing="2",
            padding="10px 12px",
            background=_PANEL,
            border_bottom=f"1px solid {GRAY_200}",
            cursor="pointer",
        ),
        # Clips grid (hidden when collapsed)
        rx.cond(
            is_collapsed,
            rx.fragment(),
            rx.box(
                rx.grid(
                    rx.foreach(
                        LumeState.filtered_clips,
                        lambda c: rx.cond(
                            c.scene_id == scene.scene_id,
                            clip_card(c),
                            rx.fragment(),
                        ),
                    ),
                    columns="2", spacing="2", width="100%",
                ),
                padding="8px",
                width="100%",
            ),
        ),
        width="100%", spacing="0",
        border_bottom=f"1px solid {GRAY_100}",
    )


# ── Library panel ─────────────────────────────────────────────────────────────

def library_panel() -> rx.Component:
    return rx.vstack(

        # ── Section header ────────────────────────────────────────────────────
        rx.hstack(
            rx.text("LIBRARY", size="1", weight="bold", color=GRAY_400,
                    letter_spacing="0.07em"),
            rx.spacer(),
            rx.box(
                rx.text(
                    LumeState.filtered_clip_count.to_string() + " clips",
                    size="1", weight="bold", color=_G600,
                ),
                background=GRAY_100, border_radius="999px", padding="2px 9px",
            ),
            width="100%", align="center",
            padding="14px 16px 10px",
        ),

        # ── Filters ───────────────────────────────────────────────────────────
        rx.cond(
            LumeState.has_project,
            rx.vstack(
                # Show row — People | Nature | All
                rx.vstack(
                    rx.hstack(
                        rx.text("Show", size="2", weight="medium", color=GRAY_400,
                                white_space="nowrap", flex_shrink="0"),
                        _filter_chip(
                            rx.cond(
                                LumeState.people_detected_count > 0,
                                "👤 People (" + LumeState.people_detected_count.to_string() + ")",
                                "👤 People",
                            ),
                            "people", LumeState.filter_show,
                            LumeState.set_filter_show("people"), GREEN,
                        ),
                        _filter_chip("🌿 Nature", "nature", LumeState.filter_show,
                                     LumeState.set_filter_show("nature"), TEAL),
                        _filter_chip("All", "all", LumeState.filter_show,
                                     LumeState.set_filter_show("all"), _PURPLE),
                        spacing="2", align="center", flex_wrap="wrap",
                    ),
                    # Warning when People filter is active but Scout hasn't run
                    rx.cond(
                        (LumeState.filter_show == "people") & ~LumeState.scout_has_run,
                        rx.hstack(
                            rx.icon("info", size=11, color=AMBER),
                            rx.text("Run Scout to detect people in clips",
                                    size="1", color=AMBER),
                            spacing="1", align="center", padding_left="52px",
                        ),
                        rx.fragment(),
                    ),
                    spacing="1", width="100%",
                ),
                # Format row — Landscape | Portrait | All
                rx.hstack(
                    rx.text("Format", size="2", weight="medium", color=GRAY_400,
                            white_space="nowrap", flex_shrink="0"),
                    _filter_chip("⬛ Land", "landscape", LumeState.filter_orientation,
                                 LumeState.set_filter_orientation("landscape"), TEAL),
                    _filter_chip("▮ Port", "portrait", LumeState.filter_orientation,
                                 LumeState.set_filter_orientation("portrait"), _PURPLE),
                    _filter_chip("All", "all", LumeState.filter_orientation,
                                 LumeState.set_filter_orientation("all"), _PURPLE),
                    spacing="2", align="center", flex_wrap="wrap",
                ),
                # Status row — Favs | High Quality
                rx.hstack(
                    rx.text("Status", size="2", weight="medium", color=GRAY_400,
                            white_space="nowrap", flex_shrink="0"),
                    _toggle_chip("★ Favs", LumeState.filter_favorites,
                                 LumeState.toggle_filter_favorites, AMBER),
                    _toggle_chip("⚡ High Quality", LumeState.filter_high_quality,
                                 LumeState.toggle_filter_high_quality, CORAL),
                    spacing="2", align="center", flex_wrap="wrap",
                ),
                padding="10px 16px",
                padding_bottom="14px",
                spacing="2",
                width="100%",
            ),
            rx.fragment(),
        ),

        # ── Vibe slider ───────────────────────────────────────────────────────
        rx.cond(
            LumeState.clips.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.text("VIBE SCORE", size="1", weight="bold", color=GRAY_400,
                            letter_spacing="0.05em"),
                    rx.spacer(),
                    rx.text(
                        "≥ " + LumeState.vibe_min_score.to_string(),
                        size="1", weight="bold", color=TEAL,
                    ),
                    width="100%", align="center",
                ),
                rx.slider(
                    default_value=[0], min=0, max=10, step=0.5,
                    on_value_commit=LumeState.set_vibe_min,
                    width="100%", color_scheme="teal",
                ),
                rx.hstack(
                    rx.text("0", size="1", color=GRAY_400),
                    rx.spacer(),
                    rx.text("10", size="1", color=GRAY_400),
                    width="100%",
                ),
                width="100%", spacing="1",
                padding="10px 16px",
                padding_bottom="14px",
            ),
            rx.fragment(),
        ),

        # ── Clip grid (flat or scene-grouped) ─────────────────────────────────
        rx.cond(
            LumeState.clips.length() == 0,
            rx.center(
                rx.vstack(
                    rx.icon("film", size=32, color=GRAY_200),
                    rx.text("No clips indexed yet.", size="2", color=GRAY_400,
                            text_align="center"),
                    rx.text("Run the Librarian to scan your source folder.",
                            size="1", color=GRAY_400, text_align="center"),
                    spacing="2", align="center",
                ),
                padding_top="32px", width="100%",
            ),
            rx.cond(
                LumeState.scenes.length() > 0,
                # Scene-grouped view
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(LumeState.scenes, _scene_group),
                        spacing="0", width="100%",
                    ),
                    height="calc(100vh - 320px)",
                    width="100%",
                    padding="8px",
                ),
                # Flat grid (no scenes yet)
                rx.scroll_area(
                    rx.grid(
                        rx.foreach(LumeState.filtered_clips, clip_card),
                        columns="2", spacing="2", width="100%",
                    ),
                    height="calc(100vh - 320px)",
                    width="100%",
                    padding="12px",
                ),
            ),
        ),

        spacing="0", width="100%", align="start",
    )


# ── Commit entry (Version Timeline) ──────────────────────────────────────────

def _commit_type_icon(message: rx.Var) -> rx.Component:
    """Return an emoji icon based on the commit message prefix."""
    return rx.match(
        message.split(":")[0].upper(),
        ("INIT",    rx.text("🌱", font_size="12px")),
        ("WATCH",   rx.text("👁",  font_size="12px")),
        ("ACTION",  rx.cond(
            message.contains("FCPXML"),  rx.text("🏗", font_size="12px"),
            rx.cond(
                message.contains("LUT") | message.contains("Color"),
                rx.text("🎨", font_size="12px"),
                rx.cond(
                    message.contains("Scout") | message.contains("Scouting"),
                    rx.text("🔭", font_size="12px"),
                    rx.cond(
                        message.contains("Index") | message.contains("Librarian"),
                        rx.text("📚", font_size="12px"),
                        rx.text("⚡", font_size="12px"),
                    ),
                ),
            ),
        )),
        rx.text("📝", font_size="12px"),
    )


def commit_entry(entry: CommitEntry) -> rx.Component:
    push_color = rx.cond(entry.pushed, GREEN, AMBER)

    return rx.hstack(
        rx.box(
            _commit_type_icon(entry.message),
            width="24px", height="24px", border_radius="7px",
            background=rx.cond(entry.pushed, f"{GREEN}12", f"{AMBER}12"),
            display="flex", align_items="center", justify_content="center",
            flex_shrink="0",
        ),
        rx.vstack(
            rx.text(
                entry.message, size="3", weight="medium", color=GRAY_900,
                overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
            ),
            rx.text(entry.created_at, size="2", color=GRAY_400),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        rx.box(
            width="7px", height="7px", border_radius="50%",
            background=push_color, flex_shrink="0",
            margin_top="8px",
        ),
        padding_y="10px", padding_x="10px", background=_PANEL,
        border=f"1px solid {GRAY_100}",
        border_radius="8px", width="100%",
        align="center", spacing="2",
        _hover={"background": GRAY_100},
        transition="background 0.1s",
    )


# ── Date-grouped timeline helpers ─────────────────────────────────────────────

def _date_label(date_str: rx.Var) -> rx.Component:
    return rx.text(
        date_str, size="1", weight="bold", color=GRAY_400,
        letter_spacing="0.06em", text_transform="uppercase",
        padding_bottom="4px", padding_left="2px",
    )


# ── GitHub status pill ────────────────────────────────────────────────────────

def github_status_pill() -> rx.Component:
    color = rx.match(
        LumeState.push_status_state,
        ("synced", GREEN), ("pending", AMBER), ("auth_failed", CORAL),
        GRAY_400,
    )
    icon_name = rx.match(
        LumeState.push_status_state,
        ("synced", "github"), ("pending", "cloud-upload"), ("auth_failed", "alert-circle"),
        "github",
    )
    return rx.hstack(
        rx.box(width="7px", height="7px", border_radius="50%", background=color),
        rx.text(LumeState.push_status_label, size="1", weight="bold", color=color),
        padding="4px 10px", border=f"1.5px solid", border_color=color,
        border_radius="999px", align="center", spacing="1",
    )


# ── Version Timeline ──────────────────────────────────────────────────────────

def version_timeline() -> rx.Component:
    # ── Collapsed view ────────────────────────────────────────────────────────
    collapsed = rx.vstack(
        rx.button(
            rx.icon("chevron-left", size=14),
            on_click=LumeState.toggle_timeline,
            background="transparent", color=GRAY_400, border="none",
            cursor="pointer", padding="6px", border_radius="8px",
            _hover={"color": _PURPLE, "background": GRAY_100},
            title="Expand timeline",
        ),
        rx.box(
            rx.text(
                "T I M E L I N E",
                size="1", weight="bold", color=GRAY_400,
                style={"writing_mode": "vertical-rl", "letter_spacing": "0.12em"},
            ),
            padding_y="12px",
        ),
        align="center", width="100%", padding_top="10px", spacing="2",
    )

    # ── Expanded view ─────────────────────────────────────────────────────────
    expanded = rx.vstack(
        # Header row
        rx.hstack(
            rx.text("TIMELINE", size="1", weight="bold", color=GRAY_400,
                    letter_spacing="0.07em"),
            rx.spacer(),
            github_status_pill(),
            rx.button(
                rx.icon("refresh-cw", size=12),
                on_click=LumeState.refresh_push_status,
                background="transparent", color=GRAY_400, border="none",
                cursor="pointer", padding="4px 6px", border_radius="6px",
                _hover={"color": GRAY_700, "background": GRAY_100},
                title="Refresh",
            ),
            rx.button(
                rx.icon("panel-right-close", size=14),
                on_click=LumeState.toggle_timeline,
                background="transparent", color=GRAY_400, border="none",
                cursor="pointer", padding="4px 6px", border_radius="6px",
                _hover={"color": _PURPLE, "background": GRAY_100},
                title="Collapse timeline",
            ),
            width="100%", align="center",
            padding="14px 16px 10px",
        ),

        rx.cond(
            LumeState.commits.length() == 0,
            rx.center(
                rx.vstack(
                    rx.icon("git-commit-horizontal", size=28, color=GRAY_200),
                    rx.text("No commits yet.", size="2", color=GRAY_400),
                    spacing="2", align="center",
                ),
                padding_top="24px", width="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(LumeState.commits, commit_entry),
                    spacing="1", width="100%", align="start",
                ),
                height="calc(100vh - 80px)",
                width="100%",
                padding="12px",
            ),
        ),

        spacing="0", width="100%", align="start",
    )

    return rx.cond(LumeState.timeline_collapsed, collapsed, expanded)


# ── Agent run button ──────────────────────────────────────────────────────────

def _agent_run_button(label: str, color: str, on_click, enabled) -> rx.Component:
    if isinstance(enabled, bool) and not enabled:
        return rx.button(
            label, disabled=True,
            background=GRAY_200, color=GRAY_400, border_radius="7px",
            padding="0 14px", height="48px", font_size="16px",
            font_weight="700", cursor="not-allowed", border="none",
            margin_top="8px",
        )
    return rx.button(
        label, on_click=on_click, disabled=~enabled,
        background=rx.cond(enabled, color, GRAY_200),
        color=rx.cond(enabled, WHITE, GRAY_400),
        border_radius="7px", padding="0 14px", height="48px",
        font_size="16px", font_weight="700",
        cursor=rx.cond(enabled, "pointer", "not-allowed"), border="none",
        _hover={"opacity": rx.cond(enabled, "0.85", "1")},
        transition="all 0.12s ease",
        margin_top="8px",
    )


# ── Header ────────────────────────────────────────────────────────────────────

def header() -> rx.Component:
    return rx.hstack(
        # Logo
        rx.hstack(
            rx.box(
                rx.text("✦", font_size="13px", color=WHITE, font_weight="900"),
                width="28px", height="28px",
                background=_GRAD_PURPLE_PINK,
                border_radius="9px",
                display="flex", align_items="center", justify_content="center",
            ),
            rx.text("Lume", size="4", weight="bold", color=GRAY_900,
                    letter_spacing="-0.04em"),
            spacing="2", align="center",
        ),

        # Divider
        rx.box(width="1px", height="18px", background=GRAY_200, flex_shrink="0"),

        # Project breadcrumb / switcher
        rx.cond(
            LumeState.has_project,
            rx.button(
                rx.hstack(
                    rx.text("Project", size="1", color=GRAY_400, weight="medium"),
                    rx.text(LumeState.project_name, size="3", color=GRAY_900,
                            weight="bold"),
                    rx.icon("chevron-down", size=13, color=GRAY_400),
                    spacing="1", align="center",
                ),
                on_click=LumeState.open_projects_panel,
                background=_PANEL, border=f"1px solid {GRAY_200}",
                border_radius="8px", padding="0 10px", height="32px",
                cursor="pointer",
                _hover={"background": GRAY_100},
                transition="background 0.1s",
            ),
            rx.button(
                rx.hstack(
                    rx.icon("folder-open", size=13, color=GRAY_400),
                    rx.text("Open project", size="1", color=GRAY_400),
                    spacing="1", align="center",
                ),
                on_click=LumeState.open_projects_panel,
                background=_PANEL, border=f"1px solid {GRAY_200}",
                border_radius="8px", padding="0 10px", height="32px",
                cursor="pointer", _hover={"background": GRAY_100},
            ),
        ),

        rx.spacer(),

        # Agent buttons grouped in a pill container
        rx.hstack(
            rx.text("AGENTS", size="1", weight="bold", color=GRAY_400,
                    letter_spacing="0.06em", padding_x="4px"),
            _agent_run_button("Librarian", TEAL, LumeState.run_librarian,
                              LumeState.librarian_enabled),
            _agent_run_button("Scout", _PURPLE, LumeState.run_scout,
                              LumeState.scout_enabled),
            _agent_run_button("Colorist", AMBER, LumeState.run_colorist,
                              LumeState.colorist_enabled),
            _agent_run_button("Architect", CORAL, LumeState.run_architect,
                              LumeState.architect_enabled),
            spacing="1", align="center",
            background=_PANEL, border=f"1px solid {GRAY_200}",
            border_radius="12px", padding="16px",
        ),

        # Watch toggle
        rx.cond(
            LumeState.has_project,
            rx.button(
                rx.cond(
                    LumeState.watcher_active,
                    rx.hstack(rx.icon("eye-off", size=13), rx.text("Stop Watch"),
                               spacing="1", align="center"),
                    rx.hstack(rx.icon("eye", size=13), rx.text("Watch"),
                               spacing="1", align="center"),
                ),
                on_click=LumeState.toggle_watcher,
                background=rx.cond(LumeState.watcher_active, GREEN, f"{GREEN}15"),
                color=rx.cond(LumeState.watcher_active, WHITE, GREEN),
                border=f"1.5px solid {GREEN}",
                border_radius="8px", padding="0 12px", height="32px",
                font_size="12px", font_weight="600", cursor="pointer",
                _hover={"opacity": "0.85"}, transition="all 0.15s ease",
            ),
            rx.fragment(),
        ),

        # Divider
        rx.box(width="1px", height="18px", background=GRAY_200, flex_shrink="0"),

        # New project
        rx.button(
            rx.hstack(rx.icon("plus", size=13), rx.text("New"),
                      spacing="1", align="center"),
            on_click=LumeState.open_create_dialog,
            background=_GRAD_PURPLE_PINK, color=WHITE, border_radius="10px",
            padding="0 14px", height="32px", font_size="12px", font_weight="700",
            border="none", cursor="pointer", _hover={"opacity": "0.85"},
        ),

        padding_x="28px", height="80px", width="100%", align="center",
        background=_BG, border_bottom=f"1px solid {GRAY_200}",
        position="sticky", top="0", z_index="100", spacing="2",
    )


# ── Export banner ─────────────────────────────────────────────────────────────

def export_banner() -> rx.Component:
    return rx.cond(
        LumeState.last_fcpxml_path != "",
        rx.hstack(
            rx.icon("file-check", size=15, color=CORAL),
            rx.text(
                "FCPXML ready — ",
                rx.text.span(LumeState.last_fcpxml_path,
                             font_weight="600", color=CORAL),
                size="2", color=GRAY_700,
            ),
            rx.spacer(),
            rx.button(
                rx.hstack(rx.icon("folder-open", size=13),
                          rx.text("Reveal in Finder"),
                          spacing="1", align="center"),
                on_click=LumeState.reveal_in_finder,
                background=CORAL, color=WHITE, border="none",
                border_radius="6px", padding="0 12px", height="26px",
                font_size="11px", font_weight="600", cursor="pointer",
                _hover={"opacity": "0.85"},
            ),
            padding_x="20px", padding_y="7px", width="100%", align="center",
            background=f"{_PANEL}",
            border_bottom=f"1px solid {_PURPLE}25",
            spacing="3",
        ),
        rx.fragment(),
    )


# ── Edit Diary (Summary tab) ─────────────────────────────────────────────────

def _commit_mini_row(entry: CommitEntry) -> rx.Component:
    """A compact commit row used inside a day group card."""
    icon = rx.match(
        entry.message.split(":")[0].upper(),
        ("INIT",   rx.text("🌱", font_size="11px")),
        ("WATCH",  rx.text("👁",  font_size="11px")),
        ("ACTION", rx.cond(
            entry.message.contains("FCPXML"),   rx.text("🏗", font_size="11px"),
            rx.cond(
                entry.message.contains("LUT") | entry.message.contains("Color"),
                rx.text("🎨", font_size="11px"),
                rx.cond(
                    entry.message.contains("Scout") | entry.message.contains("Scouting"),
                    rx.text("🔭", font_size="11px"),
                    rx.cond(
                        entry.message.contains("Index") | entry.message.contains("Librarian"),
                        rx.text("📚", font_size="11px"),
                        rx.text("⚡", font_size="11px"),
                    ),
                ),
            ),
        )),
        rx.text("📝", font_size="11px"),
    )

    return rx.hstack(
        rx.box(
            icon, width="20px", height="20px", border_radius="5px",
            background=rx.cond(entry.pushed, f"{GREEN}12", f"{AMBER}12"),
            display="flex", align_items="center", justify_content="center",
            flex_shrink="0",
        ),
        rx.text(
            entry.message, size="2", color=GRAY_700,
            overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
            flex="1",
        ),
        rx.box(
            width="6px", height="6px", border_radius="50%",
            background=rx.cond(entry.pushed, GREEN, AMBER),
            flex_shrink="0",
        ),
        spacing="2", align="center", width="100%",
        padding="5px 8px",
        border_radius="6px",
        _hover={"background": GRAY_100},
        transition="background 0.1s",
    )


def _day_group_card(group: DaySummary) -> rx.Component:
    return rx.vstack(
        # Day header
        rx.hstack(
            rx.text(
                group.label, size="3", weight="bold", color=GRAY_900,
            ),
            rx.box(
                rx.text(
                    group.commits.length().to_string() + " commits",
                    size="1", color=_G600, weight="medium",
                ),
                background=GRAY_100, border_radius="999px", padding="1px 8px",
            ),
            width="100%", align="center", spacing="2",
        ),

        # AI summary sentence
        rx.cond(
            group.summary != "",
            rx.box(
                rx.hstack(
                    rx.text("✨", font_size="12px"),
                    rx.text(
                        group.summary, size="2", color=GRAY_700,
                        font_style="italic", flex="1",
                    ),
                    spacing="2", align="start",
                ),
                background=f"{_PURPLE}15",
                border=f"1px solid {_PURPLE}40",
                border_radius="8px",
                padding="9px 12px",
                width="100%",
            ),
            rx.cond(
                LumeState.diary_generating,
                rx.hstack(
                    rx.spinner(size="1"),
                    rx.text("Generating summary…", size="1", color=GRAY_400,
                            font_style="italic"),
                    spacing="2", align="center",
                ),
                rx.fragment(),
            ),
        ),

        # Commit list (vertical timeline)
        rx.box(
            rx.vstack(
                rx.foreach(group.commits, _commit_mini_row),
                spacing="0", width="100%",
            ),
            border_left=f"2px solid {GRAY_200}",
            padding_left="10px",
            margin_left="8px",
            width="100%",
        ),

        spacing="2", width="100%",
        padding="14px 16px",
        background=_PANEL,
        border=f"1px solid {GRAY_200}",
        border_radius="12px",
    )


def _best_clip_card(clip: ClipCard) -> rx.Component:
    """Hero card shown in the Best Clips row."""
    score_col = _score_color(clip.score)
    tags_preview = clip.tags  # Reflex foreach renders them

    return rx.vstack(
        # Thumbnail
        rx.box(
            rx.cond(
                clip.hero_frame != "",
                rx.image(
                    src=rx.get_upload_url(clip.hero_frame),
                    width="100%", height="130px", object_fit="cover",
                    border_radius="14px",
                ),
                rx.box(
                    rx.icon("film", size=22, color=GRAY_400),
                    width="100%", height="130px", background=GRAY_100,
                    border_radius="14px", display="flex",
                    align_items="center", justify_content="center",
                ),
            ),
            # Score badge
            rx.box(
                rx.text(clip.score.to_string(), size="1", weight="bold",
                        color=WHITE),
                position="absolute", top="7px", right="7px",
                background=score_col, padding="2px 7px",
                border_radius="999px",
            ),
            # People badge
            rx.cond(
                clip.has_people == 1,
                rx.box(
                    rx.text("👤", font_size="10px"),
                    position="absolute", bottom="7px", right="7px",
                    background="rgba(255,255,255,0.85)",
                    padding="2px 5px", border_radius="6px",
                ),
                rx.fragment(),
            ),
            position="relative", width="100%", flex_shrink="0",
        ),
        # Tags row
        rx.hstack(
            rx.foreach(
                tags_preview,
                lambda t: rx.box(
                    rx.text(t, size="1", color=_PURPLE, weight="medium"),
                    background=f"{_PURPLE}10",
                    padding="1px 7px", border_radius="999px",
                ),
            ),
            flex_wrap="wrap", spacing="1",
        ),
        # Filename
        rx.text(
            clip.filename, size="2", color=GRAY_700,
            overflow="hidden", text_overflow="ellipsis",
            white_space="nowrap", width="100%",
        ),
        width="170px", min_width="170px", spacing="2",
        padding="10px",
        background=_PANEL,
        border=f"1.5px solid {GRAY_200}",
        border_radius="16px",
        flex_shrink="0",
    )


def summary_view() -> rx.Component:
    return rx.scroll_area(
        rx.vstack(

            # ── Your Best Clips ───────────────────────────────────────────────
            rx.cond(
                LumeState.best_clips.length() > 0,
                rx.vstack(
                    rx.hstack(
                        rx.box(
                            rx.text("⭐", font_size="14px"),
                            width="32px", height="32px", border_radius="9px",
                            background=f"#F59E0B",
                            display="flex", align_items="center",
                            justify_content="center", flex_shrink="0",
                        ),
                        rx.vstack(
                            rx.text("Your Best Clips", size="6", weight="medium",
                                    color=GRAY_900),
                            rx.text(
                                "Top-scored footage from your library",
                                size="2", color=GRAY_400,
                            ),
                            spacing="0", align="start", flex="1",
                        ),
                        rx.button(
                            rx.cond(
                                LumeState.best_clips_story_running,
                                rx.hstack(rx.spinner(size="2"), rx.text("Writing…"),
                                          spacing="2", align="center"),
                                rx.hstack(rx.icon("sparkles", size=13),
                                          rx.text("Explain These"),
                                          spacing="1", align="center"),
                            ),
                            on_click=LumeState.generate_best_clips_story,
                            disabled=~LumeState.best_clips_story_enabled,
                            background=rx.cond(
                                LumeState.best_clips_story_enabled,
                                "#F59E0B", GRAY_200,
                            ),
                            color=rx.cond(
                                LumeState.best_clips_story_enabled, GRAY_900, GRAY_400,
                            ),
                            border="none", border_radius="10px",
                            padding="0 14px", height="34px",
                            font_size="12px", font_weight="700",
                            cursor=rx.cond(
                                LumeState.best_clips_story_enabled, "pointer", "not-allowed",
                            ),
                            flex_shrink="0",
                            _hover={"opacity": rx.cond(
                                LumeState.best_clips_story_enabled, "0.88", "1",
                            )},
                        ),
                        spacing="2", align="center", width="100%",
                    ),
                    # Story paragraph
                    rx.cond(
                        LumeState.best_clips_story != "",
                        rx.box(
                            rx.hstack(
                                rx.text("✦", font_size="13px", color="#F59E0B"),
                                rx.text(
                                    LumeState.best_clips_story,
                                    size="2", color=GRAY_700,
                                    font_style="italic",
                                    line_height="1.7",
                                    flex="1",
                                ),
                                spacing="2", align="start",
                            ),
                            background=f"#F59E0B15",
                            border=f"1.5px solid #F59E0B40",
                            border_radius="12px",
                            padding="12px 14px",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    rx.scroll_area(
                        rx.hstack(
                            rx.foreach(LumeState.best_clips, _best_clip_card),
                            spacing="3", align="start",
                            padding_bottom="8px",
                        ),
                        width="100%",
                        scrollbars="horizontal",
                    ),
                    width="100%", spacing="3",
                    padding="16px",
                    background=_PANEL,
                    border=f"1.5px solid {GRAY_200}",
                    border_radius="16px",
                ),
                rx.fragment(),
            ),

            # ── Creative Suggestions ──────────────────────────────────────────
            rx.vstack(
                rx.hstack(
                    rx.box(
                        rx.text("💡", font_size="14px"),
                        width="30px", height="30px", border_radius="9px",
                        background=_GRAD_PURPLE_PINK,
                        display="flex", align_items="center",
                        justify_content="center", flex_shrink="0",
                    ),
                    rx.vstack(
                        rx.text("Creative Suggestions", size="6", weight="medium",
                                color=GRAY_900),
                        rx.text(
                            "AI-powered font, transition & edit recommendations",
                            size="1", color=GRAY_400,
                        ),
                        spacing="0", align="start", flex="1",
                    ),
                    rx.button(
                        rx.cond(
                            LumeState.creative_suggestions_running,
                            rx.hstack(rx.spinner(size="2"), rx.text("Thinking…"),
                                      spacing="2", align="center"),
                            rx.hstack(rx.icon("sparkles", size=13),
                                      rx.text("Get Suggestions"),
                                      spacing="1", align="center"),
                        ),
                        on_click=LumeState.generate_creative_suggestions,
                        disabled=~LumeState.creative_suggestions_enabled,
                        background=rx.cond(
                            LumeState.creative_suggestions_enabled,
                            _GRAD_PURPLE_PINK, GRAY_200,
                        ),
                        color=rx.cond(
                            LumeState.creative_suggestions_enabled, WHITE, GRAY_400,
                        ),
                        border="none", border_radius="10px",
                        padding="0 14px", height="34px",
                        font_size="12px", font_weight="700",
                        cursor=rx.cond(
                            LumeState.creative_suggestions_enabled,
                            "pointer", "not-allowed",
                        ),
                        flex_shrink="0",
                        _hover={"opacity": rx.cond(
                            LumeState.creative_suggestions_enabled, "0.85", "1",
                        )},
                    ),
                    width="100%", align="center", spacing="2",
                ),
                # Suggestions content
                rx.cond(
                    LumeState.creative_suggestions != "",
                    rx.box(
                        rx.text(
                            LumeState.creative_suggestions,
                            size="2", color=GRAY_700,
                            white_space="pre-wrap",
                            line_height="1.7",
                        ),
                        background=f"{_PURPLE}15",
                        border=f"1.5px solid {_PURPLE}40",
                        border_radius="12px",
                        padding="14px 16px",
                        width="100%",
                    ),
                    rx.cond(
                        LumeState.creative_suggestions_enabled,
                        rx.box(
                            rx.text(
                                "Click Get Suggestions to receive font pairings, "
                                "transition styles, and color direction based on your clips.",
                                size="1", color=GRAY_400, text_align="center",
                            ),
                            padding_y="8px", width="100%",
                        ),
                        rx.box(
                            rx.text("Run the Librarian to index clips first.",
                                    size="1", color=GRAY_400),
                            padding_y="8px",
                        ),
                    ),
                ),
                width="100%", spacing="3",
                padding="16px",
                background=_PANEL,
                border=f"1.5px solid {GRAY_200}",
                border_radius="16px",
            ),

            # ── Edit Diary ────────────────────────────────────────────────────
            rx.vstack(
                rx.hstack(
                    rx.box(
                        rx.text("📓", font_size="14px"),
                        width="30px", height="30px", border_radius="9px",
                        background=TEAL,
                        display="flex", align_items="center",
                        justify_content="center", flex_shrink="0",
                    ),
                    rx.vstack(
                        rx.text("Edit Diary", size="6", weight="medium", color=GRAY_900),
                        rx.text(
                            "Your project history, explained in plain English",
                            size="1", color=GRAY_400,
                        ),
                        spacing="0", align="start", flex="1",
                    ),
                    rx.button(
                        rx.cond(
                            LumeState.diary_generating,
                            rx.hstack(rx.spinner(size="2"), rx.text("Generating…"),
                                       spacing="2", align="center"),
                            rx.hstack(rx.icon("sparkles", size=13),
                                       rx.text("Summarize"),
                                       spacing="1", align="center"),
                        ),
                        on_click=LumeState.generate_diary,
                        disabled=~LumeState.diary_enabled,
                        background=rx.cond(
                            LumeState.diary_enabled,
                            TEAL, GRAY_200,
                        ),
                        color=rx.cond(LumeState.diary_enabled, WHITE, GRAY_400),
                        border="none", border_radius="10px",
                        padding="0 14px", height="34px",
                        font_size="12px", font_weight="700",
                        cursor=rx.cond(LumeState.diary_enabled, "pointer", "not-allowed"),
                        flex_shrink="0",
                        _hover={"opacity": rx.cond(LumeState.diary_enabled, "0.85", "1")},
                    ),
                    width="100%", align="center", spacing="2",
                ),
                # Day groups
                rx.cond(
                    LumeState.grouped_commits.length() == 0,
                    rx.center(
                        rx.vstack(
                            rx.icon("git-commit-horizontal", size=28, color=GRAY_200),
                            rx.text("No commits yet.", size="2", color=GRAY_400),
                            rx.text("Run agents to start building your edit history.",
                                    size="1", color=GRAY_400),
                            spacing="2", align="center",
                        ),
                        padding_y="24px", width="100%",
                    ),
                    rx.vstack(
                        rx.foreach(LumeState.grouped_commits, _day_group_card),
                        spacing="3", width="100%",
                    ),
                ),
                width="100%", spacing="3",
                padding="16px",
                background=_PANEL,
                border=f"1.5px solid {GRAY_200}",
                border_radius="16px",
            ),

            spacing="4", width="100%", align="start",
            padding="20px",
            min_height="100%",
        ),
        height="calc(100vh - 100px)",
        width="100%",
    )


# ── Color Lab ────────────────────────────────────────────────────────────────

def _lut_history_card(entry: LutEntry) -> rx.Component:
    return rx.hstack(
        rx.cond(
            entry.before_frame != "",
            rx.hstack(
                rx.image(src=rx.get_upload_url(entry.before_frame),
                         width="60px", height="38px", object_fit="cover",
                         border_radius="4px"),
                rx.image(src=rx.get_upload_url(entry.after_frame),
                         width="60px", height="38px", object_fit="cover",
                         border_radius="4px", border=f"2px solid {AMBER}"),
                spacing="1",
            ),
            rx.box(rx.icon("image-off", size=14, color=GRAY_400),
                   width="60px", height="38px", background=GRAY_100,
                   border_radius="4px", display="flex",
                   align_items="center", justify_content="center"),
        ),
        rx.vstack(
            rx.text(entry.prompt, size="1", weight="medium", color=GRAY_900,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
            rx.text(entry.created_at, size="1", color=GRAY_400),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        rx.button(
            "Assign",
            on_click=LumeState.assign_lut_to_clips(entry.lut_id),
            background=AMBER, color=WHITE, border="none", border_radius="6px",
            padding="0 10px", height="26px", font_size="11px", font_weight="600",
            cursor="pointer", flex_shrink="0", _hover={"opacity": "0.85"},
        ),
        padding="8px", background=_PANEL,
        border=f"1px solid {GRAY_100}",
        border_radius="8px", width="100%", align="center", spacing="2",
    )


# ── Audio Lab ────────────────────────────────────────────────────────────────

def _audio_track_row(track: AudioTrack) -> rx.Component:
    return rx.hstack(
        # Track name + duration
        rx.vstack(
            rx.text(track.name, size="2", weight="medium", color=GRAY_900,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
            rx.text(
                rx.cond(track.duration > 0, track.duration.to_string() + "s", "—"),
                size="1", color=GRAY_400,
            ),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        # Browser audio player
        rx.cond(
            track.preview_url != "",
            rx.el.audio(
                src=track.preview_url,
                controls=True,
                style={"height": "28px", "flex_shrink": "0",
                       "accent_color": _PURPLE, "width": "160px"},
            ),
            rx.fragment(),
        ),
        # Assign toggle
        rx.button(
            rx.cond(track.assigned, "✓ Assigned", "Assign"),
            on_click=LumeState.assign_audio(track.track_id),
            background=rx.cond(track.assigned, f"{GREEN}15", GRAY_100),
            color=rx.cond(track.assigned, GREEN, GRAY_400),
            border=rx.cond(track.assigned, f"1.5px solid {GREEN}40", f"1.5px solid {GRAY_200}"),
            border_radius="8px", padding="0 12px", height="28px",
            font_size="11px", font_weight="700", cursor="pointer",
            flex_shrink="0", _hover={"opacity": "0.85"},
        ),
        width="100%", spacing="2", align="center",
        padding="8px 10px",
        background=rx.cond(track.assigned, f"{GREEN}15", _PANEL),
        border=rx.cond(track.assigned, f"1px solid {GREEN}25", f"1px solid {GRAY_100}"),
        border_radius="10px",
        _hover={"background": GRAY_100},
        transition="all 0.12s",
    )


def _audio_group_card(group: AudioGroup) -> rx.Component:
    return rx.vstack(
        # Clip header row
        rx.hstack(
            rx.cond(
                group.hero_frame != "",
                rx.image(
                    src=rx.get_upload_url(group.hero_frame),
                    width="72px", height="50px", object_fit="cover",
                    border_radius="10px", flex_shrink="0",
                ),
                rx.box(
                    rx.icon("film", size=18, color=GRAY_400),
                    width="72px", height="50px", background=GRAY_100,
                    border_radius="10px", flex_shrink="0",
                    display="flex", align_items="center", justify_content="center",
                ),
            ),
            rx.vstack(
                rx.text(group.clip_name, size="2", weight="bold", color=GRAY_900,
                        overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
                rx.hstack(
                    rx.icon("music", size=11, color=_PINK),
                    rx.text(group.keywords, size="1", color=_G600,
                            font_style="italic", overflow="hidden",
                            text_overflow="ellipsis", white_space="nowrap"),
                    spacing="1", align="center",
                ),
                spacing="1", align="start", flex="1", min_width="0",
            ),
            width="100%", spacing="3", align="center",
        ),
        # Track list
        rx.cond(
            group.tracks.length() > 0,
            rx.vstack(
                rx.foreach(group.tracks, _audio_track_row),
                spacing="1", width="100%",
            ),
            rx.text("No audio matches yet — run Audio Agent.",
                    size="1", color=GRAY_400, font_style="italic",
                    padding_left="4px"),
        ),
        width="100%", spacing="3",
        padding="14px",
        background=_PANEL,
        border=f"1.5px solid {GRAY_200}",
        border_radius="14px",
    )


def audio_lab_view() -> rx.Component:
    return rx.vstack(
        # Header
        rx.hstack(
            rx.vstack(
                rx.text("Audio Augmentation Lab", size="6", weight="medium", color=GRAY_900),
                rx.text(
                    "Match clips to royalty-free ambient audio from Freesound.org",
                    size="2", color=GRAY_400,
                ),
                spacing="0", align="start",
            ),
            rx.spacer(),
            rx.button(
                rx.cond(
                    LumeState.audio_agent_running,
                    rx.hstack(rx.spinner(size="2"), rx.text("Running…"),
                              spacing="2", align="center"),
                    rx.hstack(rx.icon("music", size=13), rx.text("Run Audio Agent"),
                              spacing="1", align="center"),
                ),
                on_click=LumeState.run_audio_agent,
                disabled=~LumeState.audio_agent_enabled,
                background=rx.cond(
                    LumeState.audio_agent_enabled, _GRAD_PURPLE_PINK, GRAY_200,
                ),
                color=rx.cond(LumeState.audio_agent_enabled, WHITE, GRAY_400),
                border="none", border_radius="10px",
                height="36px", padding="0 16px",
                font_size="12px", font_weight="700",
                cursor=rx.cond(LumeState.audio_agent_enabled, "pointer", "not-allowed"),
                _hover={"opacity": rx.cond(LumeState.audio_agent_enabled, "0.85", "1")},
            ),
            width="100%", align="center",
        ),

        # Freesound API key input (shown if no tracks yet)
        rx.cond(
            LumeState.audio_groups.length() == 0,
            rx.vstack(
                rx.hstack(
                    rx.icon("key", size=13, color=GRAY_400),
                    rx.text("Freesound API Key (free at freesound.org)",
                            size="2", color=GRAY_700),
                    spacing="2", align="center",
                ),
                rx.hstack(
                    rx.input(
                        placeholder="Paste your Freesound API key here…",
                        value=LumeState.freesound_api_key_input,
                        on_change=LumeState.set_freesound_api_key_input,
                        type_="password",
                        width="100%",
                        border_radius="10px",
                        border=f"1.5px solid {GRAY_200}",
                        padding="8px 12px",
                        font_size="13px",
                        _focus={"border_color": _PURPLE, "outline": "none"},
                    ),
                    rx.link(
                        "Get free key →",
                        href="https://freesound.org/apiv2/apply/",
                        is_external=True,
                        color=_PURPLE,
                        font_size="12px",
                        font_weight="600",
                        white_space="nowrap",
                    ),
                    width="100%", spacing="3", align="center",
                ),
                width="100%", spacing="2",
                padding="14px",
                background=f"{_PURPLE}08",
                border=f"1.5px solid {_PURPLE}20",
                border_radius="14px",
            ),
            rx.fragment(),
        ),

        # Empty state
        rx.cond(
            LumeState.audio_groups.length() == 0,
            rx.center(
                rx.vstack(
                    rx.icon("music", size=36, color=GRAY_200),
                    rx.text("No audio matches yet.", size="3", color=GRAY_400,
                            weight="bold"),
                    rx.text(
                        "Enter your Freesound API key and click Run Audio Agent "
                        "to match clips with ambient audio.",
                        size="2", color=GRAY_400, text_align="center",
                        max_width="320px",
                    ),
                    spacing="3", align="center",
                ),
                padding_top="32px", width="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(LumeState.audio_groups, _audio_group_card),
                    spacing="3", width="100%",
                ),
                height="calc(100vh - 200px)",
                width="100%",
            ),
        ),

        padding="20px", spacing="4", width="100%", height="100%",
        align="start", overflow_y="auto",
    )


def color_lab() -> rx.Component:
    latest = LumeState.lut_history[0]

    return rx.vstack(
        # ── Smart LUT banner ─────────────────────────────────────────────────
        rx.cond(
            LumeState.smart_lut_enabled,
            rx.hstack(
                rx.box(
                    rx.text("✨", font_size="15px"),
                    width="34px", height="34px", border_radius="10px",
                    background=_GRAD_PURPLE_PINK,
                    display="flex", align_items="center",
                    justify_content="center", flex_shrink="0",
                ),
                rx.vstack(
                    rx.text("Smart LUT", size="6", weight="medium", color=GRAY_900),
                    rx.text("Analyze your top clips and auto-fill a color brief",
                            size="1", color=_G600),
                    spacing="0", align="start", flex="1",
                ),
                rx.button(
                    rx.cond(
                        LumeState.smart_lut_running,
                        rx.hstack(rx.spinner(size="2"), rx.text("Analyzing…"),
                                  spacing="2", align="center"),
                        rx.text("Auto-Fill Brief"),
                    ),
                    on_click=LumeState.generate_smart_lut,
                    disabled=LumeState.smart_lut_running,
                    background=_GRAD_PURPLE_PINK,
                    color=WHITE, border="none", border_radius="10px",
                    height="34px", padding="0 16px",
                    font_size="12px", font_weight="700",
                    cursor=rx.cond(LumeState.smart_lut_running,
                                   "wait", "pointer"),
                    _hover={"opacity": "0.88"},
                    flex_shrink="0",
                ),
                width="100%", align="center", spacing="3",
                padding="10px 14px",
                background=f"{_PURPLE}15",
                border=f"1.5px solid {_PURPLE}40",
                border_radius="14px",
            ),
            rx.fragment(),
        ),

        # Prompt input
        rx.vstack(
            rx.text("Color Brief", size="2", weight="medium", color=GRAY_700),
            rx.hstack(
                rx.text_area(
                    placeholder='"Mood like Succession, but warmer"',
                    value=LumeState.colorist_prompt,
                    on_change=LumeState.set_colorist_prompt,
                    width="100%", min_height="56px", border_radius="8px",
                    border=f"1.5px solid {GRAY_200}", padding="8px 12px",
                    font_size="13px", resize="none",
                    _focus={"border_color": AMBER, "outline": "none"},
                ),
                rx.button(
                    rx.cond(
                        LumeState.colorist_running,
                        rx.hstack(rx.spinner(size="2"), rx.text("Working…"),
                                  spacing="2", align="center"),
                        rx.hstack(rx.icon("wand", size=13), rx.text("Generate LUT"),
                                  spacing="1", align="center"),
                    ),
                    on_click=LumeState.run_colorist,
                    disabled=~LumeState.colorist_enabled,
                    background=rx.cond(LumeState.colorist_enabled, AMBER, GRAY_200),
                    color=rx.cond(LumeState.colorist_enabled, WHITE, GRAY_400),
                    border="none", border_radius="8px",
                    height="56px", padding="0 14px",
                    font_size="12px", font_weight="600",
                    cursor=rx.cond(LumeState.colorist_enabled, "pointer", "not-allowed"),
                    flex_shrink="0",
                    _hover={"opacity": rx.cond(LumeState.colorist_enabled, "0.85", "1")},
                ),
                width="100%", align="start", spacing="2",
            ),
            width="100%", spacing="2", align="start",
        ),

        # Before/After
        rx.cond(
            LumeState.lut_history.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.text("Before", size="1", weight="medium", color=GRAY_400),
                    rx.spacer(),
                    rx.text("After", size="1", weight="medium", color=AMBER),
                    width="100%",
                ),
                rx.hstack(
                    rx.cond(
                        latest.before_frame != "",
                        rx.image(src=rx.get_upload_url(latest.before_frame),
                                 width="50%", height="150px", object_fit="cover",
                                 border_radius="8px", border=f"1px solid {GRAY_200}"),
                        rx.box(rx.icon("image-off", size=22, color=GRAY_400),
                               width="50%", height="150px", background=GRAY_100,
                               border_radius="8px", display="flex",
                               align_items="center", justify_content="center"),
                    ),
                    rx.cond(
                        latest.after_frame != "",
                        rx.image(src=rx.get_upload_url(latest.after_frame),
                                 width="50%", height="150px", object_fit="cover",
                                 border_radius="8px", border=f"2px solid {AMBER}"),
                        rx.box(rx.icon("image-off", size=22, color=GRAY_400),
                               width="50%", height="150px", background=GRAY_100,
                               border_radius="8px", display="flex",
                               align_items="center", justify_content="center"),
                    ),
                    width="100%", spacing="2",
                ),
                rx.hstack(
                    rx.box(
                        rx.text(latest.prompt, size="2", color=GRAY_700,
                                font_style="italic"),
                        padding="7px 12px",
                        background=f"{AMBER}12",
                        border_radius="6px",
                        border=f"1px solid {AMBER}30",
                        flex="1",
                    ),
                    rx.button(
                        rx.hstack(rx.icon("check", size=12), rx.text("Assign to clips"),
                                  spacing="1", align="center"),
                        on_click=LumeState.assign_lut_to_clips(latest.lut_id),
                        background=AMBER, color=WHITE, border="none",
                        border_radius="8px", padding="0 12px", height="34px",
                        font_size="12px", font_weight="600", cursor="pointer",
                        flex_shrink="0", _hover={"opacity": "0.85"},
                    ),
                    width="100%", spacing="2", align="center",
                ),
                width="100%", spacing="2",
            ),
            rx.center(
                rx.vstack(
                    rx.icon("palette", size=32, color=GRAY_200),
                    rx.text("Enter a color brief above to generate your first LUT.",
                            size="2", color=GRAY_400, text_align="center"),
                    spacing="2", align="center",
                ),
                flex="1", width="100%",
            ),
        ),

        # LUT history
        rx.cond(
            LumeState.lut_history.length() > 1,
            rx.vstack(
                rx.text("History", size="2", weight="medium", color=GRAY_700),
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(LumeState.lut_history, _lut_history_card),
                        spacing="2", width="100%",
                    ),
                    max_height="180px", width="100%",
                ),
                width="100%", spacing="2", align="start",
            ),
            rx.fragment(),
        ),

        padding="16px", spacing="4", width="100%", height="100%",
        align="start", overflow_y="auto",
    )


# ── Center panel (tabbed) ─────────────────────────────────────────────────────

def _tab_btn(label: str, tab_id: str, active_color: str) -> rx.Component:
    is_active = LumeState.active_tab == tab_id
    return rx.button(
        rx.text(label, size="4", weight="medium"),
        on_click=LumeState.set_tab(tab_id),
        background=rx.cond(is_active, f"{active_color}14", "transparent"),
        color=rx.cond(is_active, active_color, GRAY_400),
        border="none",
        border_radius="10px 10px 0 0",
        padding="7px 16px",
        font_size="12px", font_weight="700",
        cursor="pointer",
        border_bottom=rx.cond(
            is_active,
            f"2.5px solid {active_color}",
            "2.5px solid transparent",
        ),
        transition="all 0.12s",
        _hover={"color": active_color},
    )


def center_panel() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            _tab_btn("💬 Thought Stream", "thought_stream", TEAL),
            _tab_btn("🎨 Color Lab",      "color_lab",      AMBER),
            _tab_btn("📋 Summary",        "summary",        _PURPLE),
            _tab_btn("🎵 Audio Lab",      "audio_lab",      _PINK),
            spacing="0", padding="0 4px",
            padding_bottom="12px", width="100%",
        ),
        rx.box(
            rx.match(
                LumeState.active_tab,
                ("thought_stream", thought_stream()),
                ("color_lab",      color_lab()),
                ("summary",        summary_view()),
                ("audio_lab",      audio_lab_view()),
                thought_stream(),   # default fallback
            ),
            flex="1", width="100%", overflow="hidden",
        ),
        spacing="0", height="100%", width="100%", align="start",
    )


# ── Projects panel (slide-in overlay) ────────────────────────────────────────

def _project_card(entry: ProjectEntry) -> rx.Component:
    return rx.box(
        rx.hstack(
            # Color dot
            rx.box(
                rx.text("🎬", font_size="16px"),
                width="36px", height="36px", border_radius="10px",
                background=_PURPLE,
                display="flex", align_items="center", justify_content="center",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(entry.name, size="3", weight="bold", color=GRAY_900),
                rx.text(
                    entry.remote.replace("https://github.com/", "github.com/"),
                    size="1", color=GRAY_400,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
                ),
                rx.hstack(
                    rx.box(rx.text(entry.clip_count.to_string() + " clips",
                                   size="1", weight="bold", color=TEAL),
                           background=f"{TEAL}12", padding="1px 8px",
                           border_radius="999px"),
                    rx.box(rx.text(entry.fav_count.to_string() + " favs",
                                   size="1", weight="bold", color=_PURPLE),
                           background=f"{_PURPLE}12", padding="1px 8px",
                           border_radius="999px"),
                    rx.cond(
                        entry.push_pending > 0,
                        rx.box(rx.text(entry.push_pending.to_string() + " pending",
                                       size="1", weight="bold", color=AMBER),
                               background=f"{AMBER}12", padding="1px 8px",
                               border_radius="999px"),
                        rx.box(rx.text("Synced", size="1", weight="bold", color=GREEN),
                               background=f"{GREEN}12", padding="1px 8px",
                               border_radius="999px"),
                    ),
                    spacing="1", flex_wrap="wrap",
                ),
                spacing="1", align="start", flex="1", min_width="0",
            ),
            rx.icon("chevron-right", size=16, color=GRAY_200, flex_shrink="0"),
            spacing="3", align="center", width="100%",
        ),
        on_click=LumeState.switch_project(entry.name),
        padding="14px 16px",
        border=rx.cond(entry.active, f"1.5px solid {TEAL}", f"1.5px solid {GRAY_200}"),
        background=rx.cond(entry.active, f"{TEAL}08", WHITE),
        border_radius="12px", cursor="pointer",
        _hover={"border_color": TEAL, "box_shadow": f"0 0 0 3px {TEAL}18"},
        transition="all 0.12s",
        width="100%",
    )


def projects_panel() -> rx.Component:
    return rx.cond(
        LumeState.show_projects_panel,
        # Backdrop
        rx.box(
            # Panel
            rx.box(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.vstack(
                            rx.text("All Projects", size="6", weight="medium",
                                    color=GRAY_900),
                            rx.text(
                                LumeState.all_projects.length().to_string() +
                                " project(s) — click to switch",
                                size="1", color=GRAY_400,
                            ),
                            spacing="0", align="start",
                        ),
                        rx.spacer(),
                        rx.button(
                            rx.icon("x", size=14),
                            on_click=LumeState.close_projects_panel,
                            background=GRAY_100, border="none",
                            border_radius="6px", padding="6px 8px",
                            cursor="pointer", color=_G600,
                            _hover={"background": GRAY_200},
                        ),
                        width="100%", align="center",
                    ),
                    # Project list
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(LumeState.all_projects, _project_card),
                            # Create new
                            rx.box(
                                rx.hstack(
                                    rx.box(
                                        rx.icon("plus", size=16, color=GRAY_400),
                                        width="36px", height="36px", border_radius="10px",
                                        background=GRAY_100, display="flex",
                                        align_items="center", justify_content="center",
                                        flex_shrink="0",
                                    ),
                                    rx.text("Create new project", size="2",
                                            weight="medium", color=GRAY_400),
                                    spacing="3", align="center",
                                ),
                                on_click=LumeState.open_create_dialog,
                                padding="14px 16px",
                                border=f"1.5px dashed {GRAY_200}",
                                border_radius="12px", cursor="pointer",
                                _hover={"border_color": TEAL, "color": TEAL,
                                        "background": f"{TEAL}05"},
                                transition="all 0.12s", width="100%",
                            ),
                            spacing="2", width="100%",
                        ),
                        flex="1", width="100%",
                    ),
                    spacing="3", height="100%", width="100%",
                    padding="20px",
                ),
                width="460px", height="100%",
                background=_PANEL, border_right=f"1px solid {GRAY_200}",
                z_index="201",
                on_click=rx.stop_propagation,
            ),
            position="fixed", inset="0", top="52px",
            background="rgba(17,24,39,0.3)",
            backdrop_filter="blur(3px)",
            z_index="200",
            on_click=LumeState.close_projects_panel,
            display="flex",
        ),
        rx.fragment(),
    )


# ── Create project dialog ─────────────────────────────────────────────────────

def _form_field(label: str, placeholder: str, value: rx.Var,
                on_change, input_type: str = "text") -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="medium", color=GRAY_700),
        rx.input(
            placeholder=placeholder, value=value, on_change=on_change,
            type=input_type, width="100%", border_radius="8px",
            border=f"1.5px solid {GRAY_200}", padding="8px 12px",
            font_size="14px",
            _focus={"border_color": TEAL, "outline": "none"},
        ),
        spacing="1", width="100%", align="start",
    )


def create_project_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(rx.fragment()),
        rx.dialog.content(
            rx.dialog.title(
                rx.text("New Project", size="5", weight="bold", color=GRAY_900),
            ),
            rx.vstack(
                _form_field("Project name", "my-film-2025",
                            LumeState.form_name, LumeState.set_form_name),
                _form_field("Source directory", "/Volumes/Media/Footage",
                            LumeState.form_source_dir, LumeState.set_form_source_dir),
                _form_field("GitHub remote URL", "https://github.com/you/my-film-2025",
                            LumeState.form_remote_url, LumeState.set_form_remote_url),
                _form_field("GitHub personal access token", "ghp_…",
                            LumeState.form_pat, LumeState.set_form_pat,
                            input_type="password"),
                rx.cond(
                    LumeState.form_error != "",
                    rx.box(rx.text(LumeState.form_error, size="2", color=CORAL),
                           background="#FEF2F2", border=f"1px solid {CORAL}40",
                           border_radius="8px", padding="10px 14px", width="100%"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", on_click=LumeState.close_create_dialog,
                                  background="transparent", color=GRAY_700,
                                  border=f"1.5px solid {GRAY_200}", border_radius="8px",
                                  padding="0 20px", height="38px", font_size="14px",
                                  cursor="pointer"),
                    ),
                    rx.button(
                        rx.cond(
                            LumeState.creating_project,
                            rx.hstack(rx.spinner(size="2"), rx.text("Creating…"),
                                      spacing="2", align="center"),
                            rx.text("Create project"),
                        ),
                        on_click=LumeState.submit_create_project,
                        disabled=LumeState.creating_project,
                        background=TEAL, color=WHITE, border="none",
                        border_radius="8px", padding="0 20px", height="38px",
                        font_size="14px", font_weight="600",
                        cursor=rx.cond(LumeState.creating_project,
                                       "not-allowed", "pointer"),
                    ),
                    justify="end", spacing="2", width="100%",
                ),
                spacing="4", width="100%", padding_top="8px",
            ),
            max_width="480px", padding="24px", border_radius="16px",
        ),
        open=LumeState.show_create_dialog,
    )
