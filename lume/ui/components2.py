"""
lume/ui/components2.py
Complete UI rebuild — light creative-tool aesthetic.
v3 (light theme)
All backend logic unchanged; only the visual layer is rebuilt here.
"""
from __future__ import annotations
import reflex as rx
from lume.state import LumeState, ClipCard, LogLine, CommitEntry, LutEntry, DaySummary, AudioGroup, AudioTrack, SceneEntry, ProjectEntry, ContentGroup, TodoItem
from lume.ui.theme2 import *

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _score_color(score: rx.Var) -> rx.Var:
    return rx.cond(score >= 8.5, SCORE_HIGH, rx.cond(score >= 6.0, SCORE_MID, SCORE_LOW))

def _score_label(score: rx.Var) -> rx.Var:
    return rx.cond(score >= 0, score.to_string(), rx.text("—"))

def _pill(text: str | rx.Var, bg: str, text_color: str = WHITE, size: str = F13) -> rx.Component:
    return rx.box(
        rx.text(text, size="1", weight="medium", color=text_color,
                font_size=size, white_space="nowrap"),
        background=bg, border_radius=R99, padding="3px 10px",
    )

def _icon_btn(icon: str, tooltip: str = "", on_click=None, color: str = TEXT_BODY) -> rx.Component:
    props = dict(
        background="transparent", border="none", cursor="pointer",
        color=color, padding=SP8, border_radius=R6,
        _hover={"background": ACTIVE, "color": TEXT_HEAD},
        transition="all 150ms ease",
    )
    if on_click:
        props["on_click"] = on_click
    return rx.box(rx.icon(icon, size=16), **props)

def _btn(label: str | rx.Var, bg: str = GRAD_EXPORT, on_click=None, disabled: rx.Var | bool = False,
         icon: str | None = None, width: str = "auto", height: str = "36px",
         font_size: str = F15) -> rx.Component:
    children = []
    if icon:
        children.append(rx.icon(icon, size=14))
    children.append(rx.text(label, font_size=font_size, weight="medium", color=WHITE))
    props = dict(
        background=rx.cond(disabled, f"rgba(112,48,200,0.3)", bg),
        border="none", border_radius=R9, height=height,
        padding="0 16px", cursor=rx.cond(disabled, "not-allowed", "pointer"),
        display="flex", align_items="center", justify_content="center",
        gap=SP8, width=width,
        _hover={"filter": rx.cond(disabled, "none", "brightness(1.12)")},
        _active={"filter": rx.cond(disabled, "none", "brightness(0.9)")},
        transition="all 150ms ease",
    )
    if on_click:
        props["on_click"] = on_click
    return rx.box(*children, **props)

def _outline_btn(label: str, on_click=None) -> rx.Component:
    props = dict(
        background="transparent",
        border="none",
        border_radius=R8, height="36px", padding="0 16px",
        cursor="pointer",
        display="flex", align_items="center", justify_content="center",
        _hover={"background": ACTIVE},
        transition="all 150ms ease",
    )
    if on_click:
        props["on_click"] = on_click
    return rx.box(
        rx.text(label, font_size=F15, weight="medium", color=TEXT_HEAD),
        **props,
    )

def _section_header(title: str, right: rx.Component | None = None) -> rx.Component:
    return rx.hstack(
        rx.text(title, font_size=F18, weight="bold", color=TEXT_HEAD, line_height="1.1"),
        rx.spacer(),
        right or rx.fragment(),
        width="100%", align="center", padding_bottom=SP16,
    )

def _divider() -> rx.Component:
    return rx.box(height="1px", background="rgba(160,80,220,0.15)", width="100%", margin=f"{SP20} 0")

def _filter_chip(label: str, value: str, current: rx.Var, on_click, accent: str = PURPLE) -> rx.Component:
    is_active = current == value
    return rx.box(
        rx.text(label, font_size=F13, weight=rx.cond(is_active, "bold", "medium"),
                color=rx.cond(is_active, WHITE, PILL_TEXT)),
        background=rx.cond(is_active, PILL_ACTIVE, PILL_DEFAULT),
        border_radius=R99, padding="4px 12px", cursor="pointer",
        on_click=on_click,
        transition="all 150ms ease",
        white_space="nowrap",
    )

def _toggle_chip(label: str, active: rx.Var, on_click, accent: str = PURPLE) -> rx.Component:
    return rx.box(
        rx.text(label, font_size=F13, weight=rx.cond(active, "bold", "medium"),
                color=rx.cond(active, WHITE, PILL_TEXT)),
        background=rx.cond(active, PILL_ACTIVE, PILL_DEFAULT),
        border_radius=R99, padding="4px 12px", cursor="pointer",
        on_click=on_click,
        transition="all 150ms ease",
        white_space="nowrap",
    )

# ─────────────────────────────────────────────────────────────────────────────
# CLIP CARD
# ─────────────────────────────────────────────────────────────────────────────

def clip_card(clip: ClipCard) -> rx.Component:
    score_col = _score_color(clip.score)

    thumbnail = rx.cond(
        clip.hero_frame != "",
        rx.image(
            src=rx.get_upload_url(clip.hero_frame),
            width="100%", aspect_ratio="16/9", object_fit="cover",
        ),
        rx.box(
            rx.icon("film", size=20, color=TEXT_IDLE),
            width="100%", aspect_ratio="16/9",
            background="linear-gradient(145deg,#ede8ff,#fde0f8)",
            display="flex", align_items="center", justify_content="center",
        ),
    )

    score_badge = rx.cond(
        clip.score >= 0,
        rx.box(
            rx.text(clip.score.to_string(), font_size=F13, weight="bold", color=WHITE),
            position="absolute", top=SP8, right=SP8,
            background=score_col,
            padding="2px 8px", border_radius=R99,
        ),
        rx.box(
            rx.text("Unscored", font_size="11px", weight="medium", color=TEXT_IDLE),
            position="absolute", top=SP8, right=SP8,
            background="rgba(160,80,220,0.12)",
            padding="2px 6px", border_radius=R99,
        ),
    )

    people_badge = rx.cond(
        clip.has_people == 1,
        rx.box(
            rx.text("👤", font_size="11px"),
            position="absolute", top=SP8, left=SP8,
        ),
        rx.fragment(),
    )

    fav_btn = rx.box(
        rx.cond(clip.is_favorite,
                rx.text("★", color=AMBER, font_size=F13),
                rx.text("☆", color=TEXT_IDLE, font_size=F13)),
        cursor="pointer",
        on_click=LumeState.toggle_favorite(clip.clip_id),
        _hover={"color": AMBER},
        transition="color 150ms ease",
        padding="0 4px",
        flex_shrink="0",
    )

    # Show first 2 tags as tiny chips
    tag_strip = rx.cond(
        clip.tags.length() > 0,
        rx.hstack(
            rx.foreach(
                clip.tags[:2],
                lambda t: rx.box(
                    rx.text(t, font_size="10px", color=TEXT_LABEL, white_space="nowrap"),
                    background="rgba(160,80,220,0.08)",
                    border_radius=R99, padding="1px 6px",
                    flex_shrink="0",
                ),
            ),
            spacing="1", flex_wrap="nowrap", overflow="hidden",
            flex="1", min_width="0",
        ),
        rx.fragment(),
    )

    return rx.box(
        rx.box(
            thumbnail,
            score_badge,
            people_badge,
            position="relative", overflow="hidden",
        ),
        rx.hstack(
            rx.vstack(
                rx.text(clip.filename, font_size=F14, weight="medium", color=TEXT_HEAD,
                        overflow="hidden", text_overflow="ellipsis",
                        white_space="nowrap", width="100%"),
                rx.hstack(
                    rx.text(clip.duration.to_string() + "s", font_size=F12, color=TEXT_LABEL,
                            flex_shrink="0"),
                    tag_strip,
                    spacing="2", align="center", width="100%",
                ),
                spacing="0", align="start", width="100%", min_width="0",
            ),
            fav_btn,
            align="center", width="100%",
            padding=f"{SP8} {SP12}",
        ),
        on_click=LumeState.open_clip_detail(clip.clip_id),
        background=rx.cond(clip.usable, CARD_BG, f"rgba(240,40,128,0.06)"),
        border_radius=R8, overflow="hidden",
        box_shadow=rx.cond(
            LumeState.selected_clip_id == clip.clip_id,
            f"0 0 0 2px {PURPLE}, {SHADOW_CARD_HOV}",
            SHADOW_CARD,
        ),
        _hover={"box_shadow": SHADOW_CARD_HOV, "transform": "translateY(-2px)"},
        transition="all 150ms ease",
        cursor="pointer",
        width="100%",
    )

# ─────────────────────────────────────────────────────────────────────────────
# LIBRARY PANEL (left sidebar)
# ─────────────────────────────────────────────────────────────────────────────

def _content_group_section(group: ContentGroup) -> rx.Component:
    is_collapsed = LumeState.collapsed_content_groups.contains(group.name)
    return rx.vstack(
        # Group header
        rx.hstack(
            rx.icon(group.icon, size=13, color=PURPLE),
            rx.text(group.name, font_size=F13, weight="bold", color=TEXT_HEAD,
                    flex="1"),
            rx.box(
                rx.text(group.clips.length().to_string(),
                        font_size="11px", weight="medium", color=TEXT_LABEL),
                background="rgba(160,80,220,0.10)", border_radius=R99,
                padding="1px 8px",
            ),
            rx.icon(
                rx.cond(is_collapsed, "chevron-right", "chevron-down"),
                size=13, color=TEXT_LABEL,
            ),
            spacing="2", align="center", width="100%",
            cursor="pointer",
            on_click=LumeState.toggle_content_group(group.name),
            padding=f"{SP4} 0",
            _hover={"color": TEXT_HEAD},
        ),
        # Clip grid (hidden when collapsed)
        rx.cond(
            ~is_collapsed,
            rx.grid(
                rx.foreach(group.clips, clip_card),
                columns="2", spacing="2", width="100%",
            ),
            rx.fragment(),
        ),
        spacing="1", width="100%",
    )


def library_panel() -> rx.Component:
    # scout warning
    scout_warn = rx.cond(
        (LumeState.filter_show == "people") & ~LumeState.scout_has_run,
        rx.hstack(
            rx.icon("info", size=12, color=AMBER),
            rx.text("Run Scout to detect people", font_size=F13, color=AMBER),
            spacing="1", align="center",
            padding=f"{SP4} 0",
        ),
        rx.fragment(),
    )

    filters = rx.vstack(
        # Show row
        rx.hstack(
            rx.text("Show", font_size=F13, color=TEXT_LABEL, white_space="nowrap",
                    flex_shrink="0", width="48px"),
            _filter_chip("People", "people", LumeState.filter_show,
                         LumeState.set_filter_show("people"), PURPLE),
            _filter_chip("Nature", "nature", LumeState.filter_show,
                         LumeState.set_filter_show("nature"), PURPLE),
            _filter_chip("All", "all", LumeState.filter_show,
                         LumeState.set_filter_show("all"), PURPLE),
            scout_warn,
            spacing="2", align="center", width="100%", flex_wrap="wrap",
        ),
        # Format row
        rx.hstack(
            rx.text("Format", font_size=F13, color=TEXT_LABEL, white_space="nowrap",
                    flex_shrink="0", width="48px"),
            _filter_chip("Land", "landscape", LumeState.filter_orientation,
                         LumeState.set_filter_orientation("landscape"), PURPLE),
            _filter_chip("Port", "portrait", LumeState.filter_orientation,
                         LumeState.set_filter_orientation("portrait"), PURPLE),
            _filter_chip("All", "all", LumeState.filter_orientation,
                         LumeState.set_filter_orientation("all"), PURPLE),
            spacing="2", align="center", width="100%",
        ),
        # Status row
        rx.hstack(
            rx.text("Status", font_size=F13, color=TEXT_LABEL, white_space="nowrap",
                    flex_shrink="0", width="48px"),
            _toggle_chip("★ Favs", LumeState.filter_favorites,
                         LumeState.toggle_filter_favorites, AMBER),
            _toggle_chip("⚡ HQ", LumeState.filter_high_quality,
                         LumeState.toggle_filter_high_quality, PURPLE),
            spacing="2", align="center", width="100%",
        ),
        spacing="2", width="100%",
    )

    sort_row = rx.hstack(
        rx.text("Sort", font_size=F13, color=TEXT_LABEL, white_space="nowrap",
                flex_shrink="0", width="36px"),
        rx.hstack(
            rx.foreach(
                [["↓ Score", "score_desc"], ["↑ Score", "score_asc"],
                 ["Duration", "duration_desc"], ["Name", "name"], ["Default", "default"]],
                lambda item: rx.box(
                    rx.text(item[0], font_size="11px",
                            weight=rx.cond(LumeState.sort_by == item[1], "bold", "medium"),
                            color=rx.cond(LumeState.sort_by == item[1], WHITE, PILL_TEXT),
                            white_space="nowrap"),
                    background=rx.cond(LumeState.sort_by == item[1], PILL_ACTIVE, PILL_DEFAULT),
                    border_radius=R99, padding="3px 8px", cursor="pointer",
                    on_click=LumeState.set_sort_by(item[1]),
                    flex_shrink="0",
                    transition="all 150ms ease",
                ),
            ),
            spacing="1", flex_wrap="wrap",
        ),
        spacing="2", align="center", width="100%",
    )

    tag_filter_row = rx.cond(
        LumeState.available_tags.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.text("Tags", font_size=F13, color=TEXT_LABEL, flex_shrink="0", width="36px"),
                rx.box(
                    rx.hstack(
                        rx.foreach(
                            LumeState.available_tags,
                            lambda tag: rx.box(
                                rx.text(tag, font_size="11px",
                                        weight=rx.cond(
                                            LumeState.filter_active_tags.contains(tag),
                                            "bold", "medium"),
                                        color=rx.cond(
                                            LumeState.filter_active_tags.contains(tag),
                                            WHITE, PILL_TEXT),
                                        white_space="nowrap"),
                                background=rx.cond(
                                    LumeState.filter_active_tags.contains(tag),
                                    PILL_ACTIVE, PILL_DEFAULT),
                                border_radius=R99, padding="3px 8px", cursor="pointer",
                                on_click=LumeState.toggle_filter_tag(tag),
                                flex_shrink="0",
                                transition="all 150ms ease",
                            ),
                        ),
                        spacing="1",
                    ),
                    overflow_x="auto", flex="1",
                ),
                spacing="2", align="center", width="100%",
            ),
            rx.cond(
                LumeState.filter_active_tags.length() > 0,
                rx.box(
                    rx.text("✕ Clear tag filters", font_size="11px", color=PURPLE,
                            cursor="pointer"),
                    on_click=LumeState.clear_tag_filters,
                ),
                rx.fragment(),
            ),
            spacing="1", width="100%",
        ),
        rx.fragment(),
    )

    empty_state = rx.center(
        rx.vstack(
            rx.icon("folder-open", size=36, color=TEXT_IDLE),
            rx.text("No clips yet", font_size=F15, color=TEXT_IDLE, weight="medium"),
            rx.text("Run the Librarian to scan your folder",
                    font_size=F13, color=TEXT_IDLE, text_align="center"),
            spacing="2", align="center",
        ),
        padding_top=SP32,
    )

    clip_grid = rx.cond(
        LumeState.clips.length() == 0,
        empty_state,
        rx.scroll_area(
            rx.cond(
                LumeState.group_by_content & (LumeState.grouped_clips.length() > 0),
                rx.vstack(
                    rx.foreach(LumeState.grouped_clips, _content_group_section),
                    spacing="3", width="100%",
                ),
                rx.grid(
                    rx.foreach(LumeState.filtered_clips, clip_card),
                    columns="2", spacing="2", width="100%",
                ),
            ),
            type="always",
            scrollbars="vertical",
            flex="1",
            min_height="0",
            width="100%",
            padding_right="8px",
        ),
    )

    return rx.vstack(
        # Header
        rx.hstack(
            rx.text("Media Library", font_size=F18, weight="bold", color=TEXT_HEAD),
            rx.spacer(),
            rx.hstack(
                rx.text(
                    LumeState.filtered_clip_count.to_string() + " clips",
                    font_size=F13, color=TEXT_LABEL,
                ),
                rx.box(
                    rx.icon("refresh-cw", size=13, color=TEXT_LABEL),
                    on_click=LumeState.refresh_library,
                    cursor="pointer", padding="4px", border_radius=R6,
                    _hover={"background": ACTIVE, "color": TEXT_HEAD},
                    transition="all 150ms ease",
                    title="Reload clips from database",
                ),
                # Auto-watch toggle
                rx.box(
                    rx.icon(
                        rx.cond(LumeState.source_watcher_active, "eye-off", "eye"),
                        size=13,
                        color=rx.cond(LumeState.source_watcher_active, PURPLE, TEXT_LABEL),
                    ),
                    on_click=LumeState.toggle_source_watcher,
                    cursor="pointer", padding="4px", border_radius=R6,
                    background=rx.cond(LumeState.source_watcher_active, "rgba(160,80,220,0.12)", "transparent"),
                    _hover={"background": ACTIVE, "color": TEXT_HEAD},
                    transition="all 150ms ease",
                    title=rx.cond(LumeState.source_watcher_active, "Stop auto-watch (watching for new clips)", "Start auto-watch"),
                ),
                # Group by content toggle
                rx.box(
                    rx.icon("layers", size=13,
                            color=rx.cond(LumeState.group_by_content, PURPLE, TEXT_LABEL)),
                    on_click=LumeState.toggle_group_by_content,
                    cursor="pointer", padding="4px", border_radius=R6,
                    background=rx.cond(LumeState.group_by_content, "rgba(160,80,220,0.12)", "transparent"),
                    _hover={"background": ACTIVE, "color": TEXT_HEAD},
                    transition="all 150ms ease",
                    title="Group by content",
                ),
                spacing="2", align="center",
            ),
            align="center", width="100%",
        ),
        # Search
        rx.hstack(
            rx.icon("search", size=14, color=TEXT_IDLE),
            rx.input(
                placeholder="Search clips...",
                font_size=F15, color=TEXT_HEAD,
                background="transparent", border="none", outline="none",
                width="100%",
                _placeholder={"color": TEXT_IDLE},
            ),
            align="center",
            background=WHITE, box_shadow=SHADOW_SEARCH,
            border_radius=R8, height="36px", padding="0 12px",
            width="100%",
            transition="box-shadow 150ms ease",
        ),
        # Filters
        filters,
        # Sort row
        sort_row,
        # Tag filter row
        tag_filter_row,
        # Vibe slider
        rx.cond(
            LumeState.clips.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.text("MIN SCORE", font_size="11px", weight="bold",
                            color=TEXT_LABEL, letter_spacing="0.06em"),
                    rx.spacer(),
                    rx.text(LumeState.vibe_min_score.to_string(),
                            font_size=F17, weight="medium", color=TEXT_HEAD),
                    width="100%", align="center",
                ),
                rx.slider(
                    min=0, max=10, step=0.5,
                    value=[LumeState.vibe_min_score],
                    on_change=LumeState.set_vibe_min,
                    color_scheme="violet", width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.fragment(),
        ),
        # Clip grid
        clip_grid,
        spacing="3",
        width="340px",
        flex_shrink="0",
        padding=SP20,
        height="100%",
        background=LEFT_BG,
        overflow="hidden",
        display="flex",
        flex_direction="column",
    )

# ─────────────────────────────────────────────────────────────────────────────
# THOUGHT STREAM
# ─────────────────────────────────────────────────────────────────────────────

AGENT_COLORS = {
    "librarian": BADGE_LIBRARIAN,
    "scout": BADGE_SCOUT,
    "colorist": BADGE_COLORIST,
    "architect": BADGE_ARCHITECT,
    "archivist": BTN_LIBRARIAN,
    "watcher": BLUE,
    "system": PURPLE,
}

def _agent_badge_for(agent: rx.Var) -> rx.Var:
    return rx.match(
        agent,
        ("librarian", BADGE_LIBRARIAN),
        ("scout", BADGE_SCOUT),
        ("colorist", BADGE_COLORIST),
        ("architect", BADGE_ARCHITECT),
        ("archivist", BTN_LIBRARIAN),
        ("watcher", BLUE),
        PURPLE,
    )

# Keep legacy alias used in commit row
def _agent_color_for(agent: rx.Var) -> rx.Var:
    return _agent_badge_for(agent)

def _log_entry(line: LogLine) -> rx.Component:
    badge_bg = _agent_badge_for(line.agent)
    return rx.hstack(
        rx.box(
            rx.text(line.agent, font_size=F12, weight="medium", color=WHITE,
                    white_space="nowrap"),
            background=badge_bg,
            padding="4px 16px", border_radius=R99, flex_shrink="0",
            display="inline-flex", align_items="center",
        ),
        rx.text(
            line.message,
            font_size=F13, color=rx.cond(line.error, "#f02880", TEXT_BODY),
            flex="1", overflow_wrap="anywhere", line_height="1.4",
        ),
        align="start", spacing="2", width="100%",
        padding="6px 0",
    )

def thought_stream() -> rx.Component:
    return rx.box(
        rx.cond(
            LumeState.log_lines.length() == 0,
            rx.center(
                rx.vstack(
                    rx.icon("terminal", size=32, color=TEXT_IDLE),
                    rx.text("No activity yet", font_size=F15, color=TEXT_IDLE),
                    rx.text("Run an agent to see logs", font_size=F13, color=TEXT_IDLE),
                    spacing="2", align="center",
                ),
                height="100%",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(LumeState.log_lines, _log_entry),
                    spacing="0", width="100%",
                    padding=f"{SP8} {SP24} {SP32}",
                ),
                id="log-scroll-area",
                type="always",
                scrollbars="vertical",
                height="100%",
                width="100%",
            ),
        ),
        flex="1",
        min_height="0",
        width="100%",
        overflow="hidden",
    )

# ─────────────────────────────────────────────────────────────────────────────
# COLOR LAB TAB
# ─────────────────────────────────────────────────────────────────────────────

def _lut_card(entry: LutEntry) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.cond(
                    entry.before_frame != "",
                    rx.image(src=rx.get_upload_url(entry.before_frame),
                             width="50%", aspect_ratio="16/9", object_fit="cover",
                             border_radius=f"{R6} 0 0 {R6}"),
                    rx.box(width="50%", aspect_ratio="16/9",
                           background="linear-gradient(145deg,#ede8ff,#fde0f8)",
                           border_radius=f"{R6} 0 0 {R6}"),
                ),
                rx.cond(
                    entry.after_frame != "",
                    rx.image(src=rx.get_upload_url(entry.after_frame),
                             width="50%", aspect_ratio="16/9", object_fit="cover",
                             border_radius=f"0 {R6} {R6} 0"),
                    rx.box(width="50%", aspect_ratio="16/9", background=ACTIVE,
                           border_radius=f"0 {R6} {R6} 0"),
                ),
                spacing="0", width="100%",
            ),
            rx.box(
                rx.text(rx.cond(entry.description != "", entry.description, entry.prompt),
                        font_size=F13, color=TEXT_BODY, overflow_wrap="anywhere"),
                padding=f"{SP8} {SP12}",
            ),
            spacing="0", width="100%",
        ),
        background=CARD_BG, border_radius=R8, box_shadow=SHADOW_CARD,
        overflow="hidden", width="100%",
    )

def color_lab() -> rx.Component:
    return rx.vstack(
        _section_header("Color Lab"),
        # Prompt input + run
        rx.vstack(
            rx.text("Color Brief", font_size=F15, weight="medium", color=TEXT_HEAD),
            rx.text_area(
                placeholder="Describe the look: warm golden hour, cool desaturated, high contrast noir…",
                value=LumeState.colorist_prompt,
                on_change=LumeState.set_colorist_prompt,
                font_size=F14, color=TEXT_HEAD, background=CARD_BG,
                border="none", border_radius=R8,
                box_shadow=SHADOW_SEARCH,
                width="100%", min_height="80px",
                _placeholder={"color": TEXT_IDLE},
                _focus={"outline": "none"},
            ),
            rx.hstack(
                _btn(
                    rx.cond(LumeState.colorist_running, "Running…", "✦ Run Colorist"),
                    bg=BTN_COLORIST, on_click=LumeState.run_colorist,
                    disabled=LumeState.colorist_running | ~LumeState.colorist_enabled,
                ),
                _btn(
                    rx.cond(LumeState.smart_lut_running, "Analyzing…", "★ Smart LUT"),
                    bg=GRAD_EXPORT, on_click=LumeState.generate_smart_lut,
                    disabled=LumeState.smart_lut_running | ~LumeState.smart_lut_enabled,
                ),
                spacing="2",
            ),
            spacing="2", width="100%",
        ),
        # LUT history
        rx.cond(
            LumeState.lut_history.length() > 0,
            rx.vstack(
                rx.text("LUT History", font_size=F17, weight="medium", color=TEXT_HEAD),
                rx.vstack(
                    rx.foreach(LumeState.lut_history, _lut_card),
                    spacing="2", width="100%",
                ),
                spacing="2", width="100%",
            ),
            rx.fragment(),
        ),
        spacing="4", width="100%", padding=f"{SP24} 56px",
    )

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY TAB
# ─────────────────────────────────────────────────────────────────────────────

def _best_clip_mini(clip: ClipCard) -> rx.Component:
    score_col = _score_color(clip.score)
    return rx.box(
        rx.cond(
            clip.hero_frame != "",
            rx.image(src=rx.get_upload_url(clip.hero_frame),
                     width="160px", height="90px", object_fit="cover"),
            rx.box(
                rx.icon("film", size=20, color=TEXT_IDLE),
                width="160px", height="90px",
                background="linear-gradient(145deg,#ede8ff,#fde0f8)",
                display="flex", align_items="center", justify_content="center",
            ),
        ),
        rx.box(
            rx.text(clip.filename, font_size=F13, weight="medium", color=TEXT_HEAD,
                    overflow="hidden", text_overflow="ellipsis",
                    white_space="nowrap", max_width="144px"),
            _pill(clip.score.to_string(), score_col),
            display="flex", justify_content="space-between",
            align_items="center", padding=f"{SP8} {SP8}",
        ),
        background=CARD_BG, border_radius=R8, overflow="hidden",
        box_shadow=SHADOW_CARD, flex_shrink="0", width="160px",
    )

def summary_view() -> rx.Component:
    return rx.vstack(
        _section_header("Summary"),

        # Best Clips
        rx.vstack(
            rx.hstack(
                rx.text("Your Best Clips", font_size=F20, weight="medium", color=TEXT_HEAD),
                rx.spacer(),
                _btn(
                    rx.cond(LumeState.best_clips_story_running, "Thinking…",
                            "✦ Explain These"),
                    bg=GRAD_EXPORT,
                    on_click=LumeState.generate_best_clips_story,
                    disabled=~LumeState.best_clips_story_enabled | LumeState.best_clips_story_running,
                ),
                align="center", width="100%",
            ),
            rx.cond(
                LumeState.best_clips_story != "",
                rx.box(
                    rx.text(LumeState.best_clips_story, font_size=F14,
                            color=TEXT_BODY, line_height="1.7"),
                    background=CARD_BG, border_radius=R8, padding=SP16,
                    box_shadow=SHADOW_CARD, width="100%",
                ),
                rx.fragment(),
            ),
            rx.cond(
                LumeState.best_clips.length() > 0,
                rx.box(
                    rx.hstack(
                        rx.foreach(LumeState.best_clips, _best_clip_mini),
                        spacing="2",
                    ),
                    overflow_x="auto", width="100%", padding_bottom=SP8,
                ),
                rx.fragment(),
            ),
            spacing="3", width="100%",
        ),

        _divider(),

        # Creative Suggestions
        rx.vstack(
            rx.hstack(
                rx.text("Creative Suggestions", font_size=F20, weight="medium", color=TEXT_HEAD),
                rx.spacer(),
                _btn(
                    rx.cond(LumeState.creative_suggestions_running, "Thinking…",
                            "✦ Generate"),
                    bg=GRAD_EXPORT,
                    on_click=LumeState.generate_creative_suggestions,
                    disabled=~LumeState.creative_suggestions_enabled | LumeState.creative_suggestions_running,
                ),
                align="center", width="100%",
            ),
            rx.cond(
                LumeState.creative_suggestions != "",
                rx.box(
                    rx.text(LumeState.creative_suggestions, font_size=F14,
                            color=TEXT_BODY, line_height="1.7", white_space="pre-wrap"),
                    background=CARD_BG, border_radius=R8, padding=SP16,
                    box_shadow=SHADOW_CARD, width="100%",
                ),
                rx.fragment(),
            ),
            spacing="3", width="100%",
        ),

        _divider(),

        # Edit Diary
        rx.vstack(
            rx.text("Edit Diary", font_size=F20, weight="medium", color=TEXT_HEAD),
            rx.cond(
                LumeState.diary_entries.length() == 0,
                rx.text("No diary entries yet. Run the Archivist to generate.",
                        font_size=F13, color=TEXT_IDLE),
                rx.vstack(
                    rx.foreach(LumeState.diary_entries, _diary_day),
                    spacing="2", width="100%",
                ),
            ),
            spacing="3", width="100%",
        ),

        spacing="4", width="100%", padding=f"{SP24} 56px",
    )

def _diary_day(day: DaySummary) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(day.label, font_size=F15, weight="medium", color=TEXT_HEAD),
                rx.spacer(),
                align="center", justify="between", width="100%",
            ),
            rx.cond(
                day.summary != "",
                rx.text(day.summary, font_size=F13, color=TEXT_BODY, line_height="1.6"),
                rx.fragment(),
            ),
            spacing="1",
        ),
        background=CARD_BG, border_radius=R8, padding=SP16,
        box_shadow=SHADOW_CARD, width="100%",
    )

# ─────────────────────────────────────────────────────────────────────────────
# AUDIO LAB TAB
# ─────────────────────────────────────────────────────────────────────────────

def _audio_track_row(track: AudioTrack) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(track.name, font_size=F14, weight="medium", color=TEXT_HEAD,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
            rx.text(track.duration.to_string() + "s · CC0", font_size=F12, color=TEXT_LABEL),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        rx.cond(
            track.preview_url != "",
            rx.el.audio(
                src=track.preview_url,
                controls=True,
                style={"height": "28px", "accent-color": PURPLE,
                       "width": "140px", "flex-shrink": "0"},
            ),
            rx.fragment(),
        ),
        rx.cond(
            track.assigned,
            _pill("✓ Assigned", BADGE_DONE),
            rx.box(
                rx.text("Assign", font_size=F12, weight="medium", color=TEXT_HEAD),
                background=PILL_DEFAULT,
                border_radius=R6, padding="3px 10px", cursor="pointer",
                on_click=LumeState.assign_audio(track.track_id),
                _hover={"background": ACTIVE},
                transition="all 150ms ease",
            ),
        ),
        align="center", spacing="2", width="100%",
        padding=f"{SP8} 0",
    )

def _audio_group_card(group: AudioGroup) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(group.clip_name, font_size=F15, weight="medium", color=TEXT_HEAD),
                rx.spacer(),
                rx.text(
                    group.tracks.length().to_string() + " matches",
                    font_size=F13, color=TEXT_LABEL,
                ),
                align="center", width="100%",
            ),
            rx.cond(
                group.keywords != "",
                rx.text(group.keywords, font_size=F12, color=TEXT_LABEL,
                        font_style="italic"),
                rx.fragment(),
            ),
            rx.vstack(
                rx.foreach(group.tracks, _audio_track_row),
                spacing="0", width="100%",
            ),
            spacing="2", width="100%",
        ),
        background=CARD_BG, border_radius=R8, box_shadow=SHADOW_CARD,
        padding=SP16, width="100%",
    )

def audio_lab() -> rx.Component:
    return rx.vstack(
        _section_header("Audio Lab"),
        rx.vstack(
            rx.hstack(
                rx.input(
                    placeholder="Freesound API key",
                    value=LumeState.freesound_api_key_input,
                    on_change=LumeState.set_freesound_api_key_input,
                    font_size=F14, color=TEXT_HEAD, background=CARD_BG,
                    border="none", border_radius=R8,
                    box_shadow=SHADOW_SEARCH,
                    height="36px", padding="0 12px", flex="1",
                    _placeholder={"color": TEXT_IDLE},
                    _focus={"outline": "none"},
                    type="password",
                ),
                _btn(
                    rx.cond(LumeState.audio_agent_running, "Running…",
                            "▶ Run Audio Agent"),
                    bg=BTN_SCOUT, on_click=LumeState.run_audio_agent,
                    disabled=LumeState.audio_agent_running | ~LumeState.audio_agent_enabled,
                ),
                spacing="2", width="100%",
            ),
            rx.text("Uses Freesound.org CC0 audio matched to your clip keywords.",
                    font_size=F13, color=TEXT_LABEL),
            spacing="2", width="100%",
        ),
        rx.cond(
            LumeState.audio_groups.length() > 0,
            rx.vstack(
                rx.foreach(LumeState.audio_groups, _audio_group_card),
                spacing="2", width="100%",
            ),
            rx.fragment(),
        ),
        spacing="4", width="100%", padding=f"{SP24} 56px",
    )

# ─────────────────────────────────────────────────────────────────────────────
# TIMELINE
# ─────────────────────────────────────────────────────────────────────────────

def _timeline_clip_block(clip: ClipCard, color: str = PURPLE) -> rx.Component:
    return rx.box(
        rx.text(clip.filename, font_size=F13, weight="medium", color=WHITE,
                overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
        background=color, border_radius=R6, height="28px",
        display="flex", align_items="center", padding="0 8px",
        margin="4px 2px", flex_shrink="0",
        min_width="80px", max_width="200px",
    )

def version_timeline() -> rx.Component:
    return rx.cond(
        LumeState.timeline_collapsed,
        # collapsed strip
        rx.box(
            rx.button(
                rx.icon("chevron-right", size=14),
                on_click=LumeState.toggle_timeline,
                background="transparent", color=TEXT_LABEL, border="none",
                cursor="pointer", _hover={"color": TEXT_HEAD},
            ),
            width="48px", background=LEFT_BG, height="100%",
            display="flex", align_items="flex-start",
            justify_content="center", padding_top=SP16,
        ),
        # expanded sidebar
        rx.vstack(
            # AI Agents section
            rx.vstack(
                rx.hstack(
                    rx.text("AI Agents", font_size=F18, weight="bold", color=TEXT_HEAD),
                    rx.spacer(),
                    rx.button(
                        rx.icon("chevron-right", size=14),
                        on_click=LumeState.toggle_timeline,
                        background="transparent", color=TEXT_LABEL, border="none",
                        cursor="pointer", _hover={"color": TEXT_HEAD},
                        title="Collapse",
                    ),
                    align="center", width="100%",
                ),
                _agent_card("Librarian", BTN_LIBRARIAN, "Indexes and clusters your media library",
                            LumeState.librarian_running, LumeState.librarian_done,
                            LumeState.librarian_enabled, LumeState.run_librarian),
                _agent_card("Scout", BTN_SCOUT, "Scores and tags clips with AI vision",
                            LumeState.scout_running, LumeState.scout_done,
                            LumeState.has_project, LumeState.run_scout),
                _agent_card("Colorist", BTN_COLORIST, "Generates LUT color grades",
                            LumeState.colorist_running, False,
                            LumeState.colorist_enabled, LumeState.run_colorist),
                _agent_card("Architect", BTN_ARCHITECT, "Assembles FCPXML from best clips",
                            LumeState.architect_running, False,
                            LumeState.architect_enabled, LumeState.open_architect_preview),
                spacing="1", width="100%",
            ),
            _divider(),
            # FCP Watch Mode toggle
            rx.hstack(
                rx.box(
                    width="6px", height="6px", border_radius="50%", flex_shrink="0",
                    background=rx.cond(LumeState.watcher_active, BLUE, "rgba(176,144,216,0.3)"),
                    style=rx.cond(
                        LumeState.watcher_active,
                        {"animation": "pulse 1.2s ease-in-out infinite"},
                        {},
                    ),
                ),
                rx.text("Watch FCP edits", font_size=F14, weight="medium",
                        color=rx.cond(LumeState.watcher_active, TEXT_HEAD, TEXT_LABEL),
                        flex="1"),
                rx.box(
                    rx.cond(
                        LumeState.watcher_active,
                        rx.text("On", font_size=F12, weight="medium", color=BLUE),
                        rx.text("Off", font_size=F12, weight="medium", color=TEXT_IDLE),
                    ),
                    on_click=LumeState.toggle_watcher,
                    cursor="pointer",
                    padding="2px 8px", border_radius=R99,
                    background=rx.cond(
                        LumeState.watcher_active,
                        "rgba(59,130,246,0.12)",
                        "rgba(176,144,216,0.1)",
                    ),
                    _hover={"background": ACTIVE},
                    transition="all 150ms ease",
                ),
                align="center", width="100%", spacing="2",
                padding="6px 10px", border_radius=R6,
                background=CARD_BG,
                title="When On: save your FCPXML from FCP into this project folder — Lume auto-commits each edit with a descriptive message",
            ),
            _divider(),
            # Version Timeline section
            rx.vstack(
                rx.text("Version Timeline", font_size=F18, weight="bold", color=TEXT_HEAD),
                rx.cond(
                    LumeState.commits.length() == 0,
                    rx.text("No commits yet.", font_size=F13, color=TEXT_IDLE,
                            padding_top=SP8),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(LumeState.commits, _commit_row),
                            spacing="0", width="100%",
                        ),
                        height="420px", width="100%",
                    ),
                ),
                spacing="2", width="100%",
            ),
            spacing="0", width="280px", flex_shrink="0", padding=SP20,
            height="100%", overflow_y="auto",
            background=RIGHT_BG, box_shadow=SHADOW_RIGHT,
        ),
    )

def _agent_card(name: str, color: str, desc: str,
                running: rx.Var, done: rx.Var,
                enabled: rx.Var, on_run) -> rx.Component:
    name_color = rx.match(
        name,
        ("Librarian", NAME_LIBRARIAN),
        ("Scout", NAME_SCOUT),
        ("Colorist", NAME_COLORIST),
        ("Architect", NAME_ARCHITECT),
        TEXT_HEAD,
    )
    btn_bg = rx.match(
        name,
        ("Librarian", BTN_LIBRARIAN),
        ("Scout", BTN_SCOUT),
        ("Colorist", BTN_COLORIST),
        ("Architect", BTN_ARCHITECT),
        GRAD_EXPORT,
    )
    status_dot = rx.cond(
        running,
        rx.box(
            width="6px", height="6px", border_radius="50%",
            background=color, flex_shrink="0",
            style={"animation": "pulse 1.2s ease-in-out infinite"},
        ),
        rx.cond(
            done,
            rx.box(width="6px", height="6px", border_radius="50%",
                   background=BADGE_DONE, flex_shrink="0"),
            rx.box(width="6px", height="6px", border_radius="50%",
                   background="rgba(176,144,216,0.3)", flex_shrink="0"),
        ),
    )
    return rx.hstack(
        status_dot,
        rx.text(name, font_size=F14, weight="medium", color=name_color,
                flex="1"),
        _btn(
            rx.cond(running, "…", "Run"),
            bg=btn_bg,
            on_click=on_run,
            disabled=running | ~enabled,
            height="26px", font_size=F12,
        ),
        align="center", width="100%", spacing="2",
        padding="6px 10px", border_radius=R6,
        background=CARD_BG,
        title=desc,
    )

def _commit_row(commit: CommitEntry) -> rx.Component:
    agent_col = _agent_color_for(
        rx.cond(commit.message.contains("librarian") | commit.message.contains("Librarian"),
                "librarian",
                rx.cond(commit.message.contains("scout") | commit.message.contains("Scout"),
                        "scout",
                        rx.cond(commit.message.contains("colorist") | commit.message.contains("Colorist"),
                                "colorist",
                                rx.cond(commit.message.contains("architect") | commit.message.contains("Architect"),
                                        "architect",
                                        "archivist"))))
    )
    return rx.hstack(
        rx.box(
            rx.box(
                width="8px", height="8px", border_radius="50%",
                background=agent_col, flex_shrink="0", margin_top="5px",
            ),
        ),
        rx.vstack(
            rx.text(commit.message, font_size=F14, weight="medium", color=TEXT_HEAD,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap"),
            rx.text(commit.created_at, font_size=F12, color=TEXT_LABEL),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        rx.cond(
            commit.pushed,
            rx.icon("cloud-check", size=14, color=GREEN),
            rx.icon("clock", size=14, color=AMBER),
        ),
        align="start", spacing="2", width="100%",
        padding=f"{SP8} 0",
        _hover={"background": ACTIVE},
        transition="background 150ms ease",
    )

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

def _tab_btn(label: str, tab_id: str) -> rx.Component:
    is_active = LumeState.active_tab == tab_id
    return rx.box(
        rx.vstack(
            rx.text(label, font_size=F15, weight="medium",
                    color=rx.cond(is_active, TEXT_HEAD, TEXT_LABEL)),
            # active underline bar
            rx.box(
                height="2px", width="100%",
                background=rx.cond(is_active, GRAD_BRAND, "transparent"),
                border_radius="1px",
            ),
            spacing="0", align="center", justify="center",
        ),
        on_click=LumeState.set_tab(tab_id),
        background="transparent",
        padding="0 16px",
        height="64px",
        cursor="pointer",
        display="flex",
        align_items="center",
        justify_content="center",
        _hover={"background": ACTIVE},
        transition="all 150ms ease",
        flex_shrink="0",
    )

def _github_pill() -> rx.Component:
    bg = rx.match(
        LumeState.push_status_state,
        ("synced", BADGE_DONE),
        ("pending", BTN_COLORIST),
        BTN_ARCHITECT,
    )
    icon = rx.match(
        LumeState.push_status_state,
        ("synced", "check"),
        ("pending", "clock"),
        "alert-circle",
    )
    return rx.hstack(
        rx.icon(icon, size=12, color=WHITE),
        rx.text(LumeState.push_status_label, font_size=F13, weight="medium", color=WHITE),
        background=bg, border_radius=R99, padding=f"{SP4} {SP12}",
        align="center", spacing="1",
    )

def header() -> rx.Component:
    project_switcher = rx.cond(
        LumeState.has_project,
        rx.box(
            rx.hstack(
                rx.icon("folder", size=13, color=TEXT_LABEL),
                rx.text(LumeState.project_name, font_size=F13, weight="medium", color=TEXT_HEAD),
                rx.icon("chevron-down", size=13, color=TEXT_LABEL),
                spacing="1", align="center",
            ),
            on_click=LumeState.open_projects_panel,
            background=ACTIVE,
            border_radius=R8, padding="0 12px", height="32px",
            cursor="pointer", display="flex", align_items="center",
            transition="all 150ms ease",
        ),
        rx.box(
            rx.hstack(
                rx.icon("folder-open", size=13, color=TEXT_LABEL),
                rx.text("Open project", font_size=F13, color=TEXT_LABEL),
                spacing="1", align="center",
            ),
            on_click=LumeState.open_projects_panel,
            background=ACTIVE,
            border_radius=R8, padding="0 12px", height="32px",
            cursor="pointer", display="flex", align_items="center",
            transition="all 150ms ease",
        ),
    )

    return rx.hstack(
        # Left — wordmark + project switcher
        rx.hstack(
            rx.html('<span class="lume-logo">Lume</span>'),
            rx.box(width="1px", height="18px",
                   background="rgba(160,80,220,0.2)", flex_shrink="0"),
            project_switcher,
            spacing="2", align="center",
        ),
        # Center — nav tabs
        rx.hstack(
            _tab_btn("Workspace", "workspace"),
            _tab_btn("Color Lab", "color_lab"),
            _tab_btn("Summary", "summary"),
            _tab_btn("🎵 Audio Lab", "audio_lab"),
            _tab_btn("✓ Tasks", "tasks"),
            spacing="0",
        ),
        rx.spacer(),
        # Right — status + actions
        rx.hstack(
            _github_pill(),
            _btn("+ New", bg=GRAD_NEW_BTN, on_click=LumeState.open_create_dialog,
                 font_size=F13),
            rx.box(
                rx.text("Preview Edit", font_size=F13, weight="medium", color=PURPLE),
                on_click=LumeState.open_architect_preview,
                background="rgba(160,80,220,0.10)",
                border_radius=R8, padding="0 14px", height="36px",
                cursor="pointer", display="flex", align_items="center",
                _hover={"background": "rgba(160,80,220,0.18)"},
                transition="all 150ms ease",
            ),
            _btn("Export to FCP", bg=GRAD_EXPORT,
                 disabled=LumeState.last_fcpxml_path == ""),
            _icon_btn("settings", on_click=LumeState.open_settings, color=TEXT_LABEL),
            rx.box(
                rx.icon("log-out", size=15, color=TEXT_LABEL),
                on_click=LumeState.logout,
                background="transparent", border="none", cursor="pointer",
                padding=SP8, border_radius=R6,
                _hover={"background": ACTIVE, "color": TEXT_HEAD},
                transition="all 150ms ease",
                title="Sign out",
            ),
            spacing="2", align="center",
        ),
        height="64px", width="100%",
        background=TOPBAR_BG, box_shadow=SHADOW_TOPBAR,
        padding="0 20px",
        align="center",
    )

# ─────────────────────────────────────────────────────────────────────────────
# PROJECT DASHBOARD + CLIP WORKSPACE
# ─────────────────────────────────────────────────────────────────────────────

def _stat_card(label: str, value: rx.Var, color: str = PURPLE) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(value.to_string(), font_size="28px", weight="bold", color=color,
                    line_height="1"),
            rx.text(label, font_size=F12, color=TEXT_LABEL, weight="medium",
                    white_space="nowrap"),
            spacing="1", align="center",
        ),
        background=CARD_BG, border_radius=R8, padding=f"{SP16} {SP20}",
        box_shadow=SHADOW_CARD, flex="1", text_align="center",
    )


def _score_histogram() -> rx.Component:
    def _bar(bucket: dict) -> rx.Component:
        return rx.vstack(
            rx.box(
                rx.box(
                    height=bucket["pct"].to_string() + "%",
                    width="100%",
                    background=bucket["color"],
                    border_radius="4px 4px 0 0",
                    transition="height 600ms ease",
                    min_height="4px",
                ),
                height="80px", width="100%",
                display="flex", align_items="flex-end",
            ),
            rx.text(bucket["count"].to_string(), font_size=F12, weight="bold",
                    color=TEXT_HEAD, text_align="center"),
            rx.text(bucket["label"], font_size="10px", color=TEXT_LABEL,
                    text_align="center", white_space="nowrap"),
            spacing="1", align="center", flex="1",
        )

    return rx.vstack(
        rx.text("Score Distribution", font_size=F15, weight="bold", color=TEXT_HEAD),
        rx.hstack(
            rx.foreach(LumeState.score_buckets, _bar),
            spacing="2", width="100%", align="end",
        ),
        spacing="3", width="100%",
    )


def project_dashboard() -> rx.Component:
    """Shown in center panel when no clip is selected."""

    empty = rx.center(
        rx.vstack(
            rx.icon("video", size=48, color=TEXT_IDLE),
            rx.text("No project open", font_size=F18, weight="bold", color=TEXT_IDLE),
            rx.text("Open or create a project to get started",
                    font_size=F14, color=TEXT_IDLE),
            spacing="2", align="center",
        ),
        height="100%",
    )

    dashboard = rx.scroll_area(
        rx.vstack(
            # Stats row
            rx.hstack(
                _stat_card("Total Clips", LumeState.clips.length(), PURPLE),
                _stat_card("Scored", LumeState.scored_clip_count, BADGE_SCOUT),
                _stat_card("Favorites", LumeState.favorites_count, AMBER),
                _stat_card("Unscored",
                           LumeState.clips.length() - LumeState.scored_clip_count,
                           TEXT_LABEL),
                spacing="3", width="100%",
            ),
            _divider(),
            # Score histogram (only when clips scored)
            rx.cond(
                LumeState.scored_clip_count > 0,
                _score_histogram(),
                rx.fragment(),
            ),
            # Top clips
            rx.cond(
                LumeState.best_clips.length() > 0,
                rx.vstack(
                    rx.cond(
                        LumeState.scored_clip_count > 0,
                        _divider(),
                        rx.fragment(),
                    ),
                    rx.text("Top Clips", font_size=F15, weight="bold", color=TEXT_HEAD),
                    rx.hstack(
                        rx.foreach(
                            LumeState.best_clips,
                            lambda clip: rx.box(
                                rx.cond(
                                    clip.hero_frame != "",
                                    rx.image(
                                        src=rx.get_upload_url(clip.hero_frame),
                                        width="100%", aspect_ratio="16/9",
                                        object_fit="cover",
                                    ),
                                    rx.box(width="100%", aspect_ratio="16/9",
                                           background=ACTIVE),
                                ),
                                rx.hstack(
                                    rx.text(clip.filename, font_size=F12, color=TEXT_HEAD,
                                            overflow="hidden", text_overflow="ellipsis",
                                            white_space="nowrap", flex="1", min_width="0"),
                                    rx.box(
                                        rx.text(clip.score.to_string(), font_size="11px",
                                                weight="bold", color=WHITE),
                                        background=SCORE_HIGH, border_radius=R99,
                                        padding="1px 6px", flex_shrink="0",
                                    ),
                                    spacing="1", align="center",
                                    padding=f"{SP4} {SP8}",
                                ),
                                on_click=LumeState.open_clip_detail(clip.clip_id),
                                background=CARD_BG, border_radius=R8,
                                overflow="hidden", box_shadow=SHADOW_CARD,
                                cursor="pointer", flex_shrink="0", width="160px",
                                _hover={"box_shadow": SHADOW_CARD_HOV,
                                        "transform": "translateY(-2px)"},
                                transition="all 150ms ease",
                            ),
                        ),
                        spacing="3", flex_wrap="wrap",
                    ),
                    spacing="3", width="100%",
                ),
                rx.fragment(),
            ),
            spacing="4", padding=f"{SP24} 56px", width="100%",
        ),
        height="100%", width="100%", background="transparent",
    )

    return rx.cond(LumeState.has_project, dashboard, empty)


def clip_workspace() -> rx.Component:
    """Full-center clip view — shown when a clip is selected in Workspace tab."""
    clip = LumeState.detail_clip
    score_col = rx.cond(
        clip.score >= 8.5, SCORE_HIGH,
        rx.cond(clip.score >= 6.0, SCORE_MID, SCORE_LOW)
    )

    return rx.scroll_area(
        rx.vstack(
            # Back nav
            rx.hstack(
                rx.icon("chevron-left", size=14, color=TEXT_LABEL),
                rx.text("Dashboard", font_size=F13, color=TEXT_LABEL),
                spacing="1", align="center",
                cursor="pointer",
                on_click=LumeState.close_clip_detail,
                _hover={"color": TEXT_HEAD},
                padding_bottom=SP8,
            ),
            # Header row
            rx.hstack(
                rx.vstack(
                    rx.text(clip.filename, font_size=F20, weight="bold", color=TEXT_HEAD,
                            overflow_wrap="anywhere"),
                    rx.text(clip.duration.to_string() + "s · " +
                            rx.cond(clip.usable, "Usable", "Culled"),
                            font_size=F13, color=TEXT_LABEL),
                    spacing="0", align="start", flex="1", min_width="0",
                ),
                rx.hstack(
                    rx.cond(
                        clip.is_favorite,
                        rx.box(
                            rx.text("★ Favorited", font_size=F13, weight="medium",
                                    color=AMBER),
                            on_click=LumeState.toggle_favorite(clip.clip_id),
                            background="rgba(240,160,32,0.12)",
                            border_radius=R8, padding="8px 14px", cursor="pointer",
                        ),
                        rx.box(
                            rx.text("☆ Favorite", font_size=F13, weight="medium",
                                    color=TEXT_BODY),
                            on_click=LumeState.toggle_favorite(clip.clip_id),
                            background=ACTIVE, border_radius=R8,
                            padding="8px 14px", cursor="pointer",
                            _hover={"background": PILL_DEFAULT},
                        ),
                    ),
                    _btn("Re-score", bg=BTN_SCOUT,
                         on_click=LumeState.run_scout,
                         disabled=LumeState.scout_running | ~LumeState.has_project,
                         font_size=F13),
                    spacing="2", align="center",
                ),
                align="start", width="100%",
            ),
            # Keyframe strip
            rx.cond(
                LumeState.selected_clip_frames.length() > 0,
                rx.box(
                    rx.hstack(
                        rx.foreach(
                            LumeState.selected_clip_frames,
                            lambda key: rx.image(
                                src=rx.get_upload_url(key),
                                height="120px", aspect_ratio="16/9",
                                object_fit="cover", border_radius=R8,
                                flex_shrink="0",
                            ),
                        ),
                        spacing="3",
                    ),
                    overflow_x="auto", width="100%",
                ),
                rx.fragment(),
            ),
            _divider(),
            # Score breakdown
            rx.cond(
                clip.score >= 0,
                rx.hstack(
                    # Big score badge
                    rx.box(
                        rx.vstack(
                            rx.text(clip.score.to_string(), font_size="40px",
                                    weight="bold", color=WHITE, line_height="1"),
                            rx.text("/ 10", font_size=F14, color="rgba(255,255,255,0.7)"),
                            spacing="0", align="center",
                        ),
                        background=score_col, border_radius=R8,
                        padding="20px 28px", flex_shrink="0",
                        display="flex", align_items="center", justify_content="center",
                    ),
                    # Breakdown bars
                    rx.vstack(
                        _score_bar("Stability", clip.stability, BADGE_SCOUT),
                        _score_bar("Focus",     clip.focus,     BADGE_COLORIST),
                        _score_bar("Lighting",  clip.lighting,  BADGE_ARCHITECT),
                        spacing="3", flex="1",
                    ),
                    spacing="4", align="center", width="100%",
                ),
                rx.box(
                    rx.text("Not yet scored — run Scout to analyse this clip.",
                            font_size=F14, color=TEXT_IDLE),
                    background=CARD_BG, border_radius=R8, padding=SP16,
                    width="100%",
                ),
            ),
            # Tags
            rx.cond(
                clip.tags.length() > 0,
                rx.vstack(
                    rx.text("Tags", font_size=F14, weight="medium", color=TEXT_HEAD),
                    rx.hstack(
                        rx.foreach(
                            clip.tags,
                            lambda t: rx.box(
                                rx.text(t, font_size=F13, color=PURPLE, weight="medium"),
                                background="rgba(160,80,220,0.10)",
                                border_radius=R99, padding="4px 12px",
                            ),
                        ),
                        flex_wrap="wrap", spacing="2",
                    ),
                    spacing="2", width="100%",
                ),
                rx.fragment(),
            ),
            spacing="4", padding=f"{SP24} 56px", width="100%",
        ),
        height="100%", width="100%",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CENTER PANEL
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# TASKS TAB
# ─────────────────────────────────────────────────────────────────────────────

def _todo_item_row(item: TodoItem) -> rx.Component:
    """Single todo row: checkbox • (AI badge) • text • delete button."""
    checkbox = rx.box(
        rx.cond(
            item.done,
            rx.icon("check-square", size=17, color=PURPLE),
            rx.icon("square", size=17, color=TEXT_LABEL),
        ),
        cursor="pointer",
        on_click=LumeState.toggle_todo(item.item_id),
        flex_shrink="0",
        padding="2px",
        _hover={"opacity": "0.8"},
        transition="opacity 150ms ease",
    )

    ai_badge = rx.cond(
        item.ai_generated,
        rx.box(
            rx.hstack(
                rx.text("✦", font_size="9px", color=PURPLE),
                rx.text("AI", font_size="10px", weight="medium", color=PURPLE),
                spacing="0",
            ),
            background="rgba(160,80,220,0.10)",
            border_radius=R99,
            padding="1px 7px",
            flex_shrink="0",
        ),
        rx.fragment(),
    )

    agent_hint = rx.cond(
        item.agent_trigger != "",
        rx.text(
            "auto-checks when " + item.agent_trigger + " runs",
            font_size="10px", color=TEXT_IDLE, font_style="italic",
            flex_shrink="0",
        ),
        rx.fragment(),
    )

    return rx.hstack(
        checkbox,
        rx.vstack(
            rx.hstack(
                ai_badge,
                rx.text(
                    item.text,
                    font_size=F14,
                    color=rx.cond(item.done, TEXT_IDLE, TEXT_HEAD),
                    text_decoration=rx.cond(item.done, "line-through", "none"),
                    flex="1", line_height="1.4",
                ),
                spacing="2", align="center", flex="1", min_width="0",
            ),
            rx.cond(
                ~item.done & (item.agent_trigger != ""),
                agent_hint,
                rx.fragment(),
            ),
            spacing="0", align="start", flex="1", min_width="0",
        ),
        rx.box(
            rx.icon("x", size=12, color=TEXT_IDLE),
            cursor="pointer",
            on_click=LumeState.delete_todo(item.item_id),
            padding="4px", border_radius=R6,
            _hover={"background": ACTIVE, "color": CORAL},
            transition="all 150ms ease",
            flex_shrink="0",
        ),
        align="start", spacing="2", width="100%",
        padding=f"{SP12} {SP16}",
        background=rx.cond(item.done, "rgba(160,80,220,0.04)", CARD_BG),
        border_radius=R8,
        box_shadow=rx.cond(item.done, "none", SHADOW_CARD),
        _hover={"box_shadow": rx.cond(item.done, "none", SHADOW_CARD_HOV)},
        transition="all 150ms ease",
    )


def tasks_view() -> rx.Component:
    """Center-panel Tasks tab — two-column layout: info+add on left, items on right."""

    progress_bar = rx.cond(
        LumeState.todo_total_count > 0,
        rx.vstack(
            rx.hstack(
                rx.text(
                    LumeState.todo_done_count.to_string() + " of " +
                    LumeState.todo_total_count.to_string() + " complete",
                    font_size=F13, color=TEXT_LABEL,
                ),
                rx.spacer(),
                rx.cond(
                    LumeState.todo_progress_pct == 100,
                    rx.hstack(
                        rx.icon("check-circle", size=13, color=GREEN),
                        rx.text("All done! 🎉", font_size=F13, weight="medium", color=GREEN),
                        spacing="1", align="center",
                    ),
                    rx.fragment(),
                ),
                align="center", width="100%",
            ),
            rx.box(
                rx.box(
                    height="100%", border_radius=R99,
                    background=GRAD_EXPORT,
                    width=LumeState.todo_progress_pct.to_string() + "%",
                    transition="width 600ms ease",
                    min_width="4px",
                ),
                height="5px", border_radius=R99,
                background="rgba(160,80,220,0.15)",
                overflow="hidden", width="100%",
            ),
            spacing="1", width="100%",
        ),
        rx.fragment(),
    )

    add_row = rx.hstack(
        rx.input(
            placeholder="Add a task and press Enter…",
            value=LumeState.todo_input,
            on_change=LumeState.set_todo_input,
            on_key_up=LumeState.add_todo_on_enter,
            font_size=F14, color=TEXT_HEAD,
            background=CARD_BG,
            border="none", border_radius=R8,
            box_shadow=SHADOW_SEARCH,
            height="40px", padding="0 14px", flex="1",
            _placeholder={"color": TEXT_IDLE},
            _focus={"outline": "none", "box_shadow": f"0 0 0 2px {PURPLE}40"},
        ),
        rx.box(
            rx.hstack(
                rx.icon("plus", size=14),
                rx.text("Add", font_size=F14, weight="medium"),
                spacing="1", align="center",
            ),
            on_click=LumeState.add_todo,
            background=GRAD_EXPORT,
            border_radius=R8, height="40px", padding="0 16px",
            cursor="pointer", display="flex", align_items="center",
            color=WHITE,
            _hover={"filter": "brightness(1.12)"},
            transition="all 150ms ease",
            flex_shrink="0",
        ),
        spacing="2", align="center", width="100%",
    )

    empty_state = rx.center(
        rx.vstack(
            rx.icon("list-checks", size=40, color=TEXT_IDLE),
            rx.text("No tasks yet", font_size=F15, color=TEXT_IDLE, weight="medium"),
            rx.text("Open a project to see AI suggestions",
                    font_size=F13, color=TEXT_IDLE, text_align="center"),
            spacing="2", align="center",
        ),
        padding_top=SP32, width="100%",
    )

    items_section = rx.cond(
        LumeState.todo_items.length() == 0,
        empty_state,
        rx.vstack(
            rx.foreach(LumeState.todo_items, _todo_item_row),
            spacing="2", width="100%", padding_bottom=SP16,
        ),
    )

    # ── Left column — checklist info + add task ───────────────────────────────
    left_col = rx.vstack(
        rx.vstack(
            rx.text("Project Checklist", font_size=F20, weight="medium", color=TEXT_HEAD),
            rx.text(
                "✦ AI tasks auto-complete when the matching agent runs",
                font_size=F13, color=TEXT_LABEL, line_height="1.5",
            ),
            spacing="1", align="start",
        ),
        progress_bar,
        rx.spacer(),
        rx.box(height="1px", background="rgba(160,80,220,0.12)", width="100%"),
        rx.vstack(
            rx.text("Add your own task", font_size=F13, weight="medium", color=TEXT_LABEL),
            add_row,
            spacing="2", width="100%",
        ),
        spacing="4", width="280px", flex_shrink="0", flex_grow="0",
        padding_right="32px",
    )

    # ── Vertical divider ──────────────────────────────────────────────────────
    divider = rx.box(
        width="1px", background="rgba(160,80,220,0.12)",
        align_self="stretch", flex_shrink="0", margin_right="32px",
    )

    # ── Right column — scrollable task list ───────────────────────────────────
    right_col = rx.vstack(
        rx.hstack(
            rx.text("Tasks", font_size=F17, weight="medium", color=TEXT_HEAD),
            rx.spacer(),
            rx.cond(
                LumeState.todo_items.length() > 0,
                rx.box(
                    rx.text(
                        LumeState.todo_done_count.to_string() + "/" +
                        LumeState.todo_total_count.to_string(),
                        font_size=F12, weight="medium", color=PURPLE,
                    ),
                    background="rgba(160,80,220,0.10)", border_radius=R99,
                    padding="3px 10px",
                ),
                rx.fragment(),
            ),
            align="center", width="100%", padding_bottom=SP8,
        ),
        rx.scroll_area(
            items_section,
            flex="1", width="100%", min_height="0",
        ),
        flex="1", min_width="0", spacing="0",
    )

    return rx.vstack(
        _section_header("Tasks"),
        rx.hstack(
            left_col,
            divider,
            right_col,
            flex="1", width="100%", min_height="0",
            spacing="0", align="stretch",
        ),
        spacing="4", width="100%", padding=f"{SP24} 56px",
        flex="1", min_height="0", overflow="hidden",
    )


def center_panel() -> rx.Component:
    # Workspace tab: clip detail when selected, dashboard otherwise
    workspace_tab = rx.cond(
        LumeState.show_clip_detail & (LumeState.detail_clip_id != ""),
        clip_workspace(),
        project_dashboard(),
    )

    tab_content = rx.cond(
        LumeState.active_tab == "color_lab",
        rx.scroll_area(color_lab(), height="100%", width="100%", background="transparent"),
        rx.cond(
            LumeState.active_tab == "summary",
            rx.scroll_area(summary_view(), height="100%", width="100%", background="transparent"),
            rx.cond(
                LumeState.active_tab == "audio_lab",
                rx.scroll_area(audio_lab(), height="100%", width="100%", background="transparent"),
                rx.cond(
                    LumeState.active_tab == "tasks",
                    tasks_view(),
                    workspace_tab,
                ),
            ),
        ),
    )

    return rx.box(
        tab_content,
        flex="1", min_height="0", overflow="hidden",
        background="transparent", min_width="0",
    )

# ─────────────────────────────────────────────────────────────────────────────
# PROJECT SWITCHER / PANEL / CREATE DIALOG
# ─────────────────────────────────────────────────────────────────────────────

def _project_card(entry: ProjectEntry) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                rx.text("🎬", font_size="15px"),
                width="34px", height="34px", border_radius=R8,
                background=GRAD_EXPORT,
                display="flex", align_items="center", justify_content="center",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(entry.name, font_size=F15, weight="bold", color=TEXT_HEAD),
                rx.text(
                    entry.remote.replace("https://github.com/", "github.com/"),
                    font_size=F12, color=TEXT_LABEL,
                    overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
                ),
                rx.hstack(
                    rx.box(rx.text(entry.clip_count.to_string() + " clips",
                                   font_size=F12, weight="medium", color=NAME_LIBRARIAN),
                           background="rgba(160,216,48,0.15)", padding="2px 8px",
                           border_radius=R99),
                    rx.cond(
                        entry.push_pending > 0,
                        rx.box(rx.text(entry.push_pending.to_string() + " pending",
                                       font_size=F12, weight="medium", color=NAME_COLORIST),
                               background="rgba(240,160,32,0.15)", padding="2px 8px",
                               border_radius=R99),
                        rx.box(rx.text("Synced", font_size=F12, weight="medium",
                                       color=NAME_LIBRARIAN),
                               background="rgba(160,216,48,0.15)", padding="2px 8px",
                               border_radius=R99),
                    ),
                    spacing="1",
                ),
                spacing="1", align="start", flex="1", min_width="0",
            ),
            rx.icon("chevron-right", size=14, color=TEXT_LABEL),
            spacing="3", align="center", width="100%",
        ),
        on_click=LumeState.switch_project(entry.name),
        padding="12px 14px",
        background=rx.cond(entry.active, "rgba(160,216,48,0.08)", CARD_BG),
        box_shadow=rx.cond(entry.active, f"0 0 0 1.5px {GREEN}", SHADOW_CARD),
        border_radius=R8, cursor="pointer",
        _hover={"box_shadow": SHADOW_CARD_HOV, "background": ACTIVE},
        transition="all 150ms ease",
        width="100%",
    )


def _form_field(label: str, placeholder: str, value: rx.Var,
                on_change, input_type: str = "text") -> rx.Component:
    return rx.vstack(
        rx.text(label, font_size=F13, weight="medium", color=TEXT_BODY),
        rx.input(
            placeholder=placeholder, value=value, on_change=on_change,
            type=input_type, width="100%", border_radius=R8,
            border="none", background=ACTIVE,
            box_shadow=SHADOW_SEARCH,
            color=TEXT_HEAD, padding="8px 12px", font_size=F14,
            _focus={"outline": "none"},
            _placeholder={"color": TEXT_IDLE},
        ),
        spacing="1", width="100%", align="start",
    )


def projects_panel() -> rx.Component:
    return rx.cond(
        LumeState.show_projects_panel,
        rx.box(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.vstack(
                            rx.text("All Projects", font_size=F20, weight="bold",
                                    color=TEXT_HEAD),
                            rx.text(
                                LumeState.all_projects.length().to_string() + " project(s) — click to switch",
                                font_size=F12, color=TEXT_LABEL,
                            ),
                            spacing="0", align="start",
                        ),
                        rx.spacer(),
                        rx.box(
                            rx.icon("x", size=14, color=TEXT_BODY),
                            on_click=LumeState.close_projects_panel,
                            background=ACTIVE,
                            border_radius=R6, padding="6px 8px",
                            cursor="pointer", _hover={"background": PILL_DEFAULT},
                        ),
                        width="100%", align="center",
                    ),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(LumeState.all_projects, _project_card),
                            rx.box(
                                rx.hstack(
                                    rx.icon("plus", size=16, color=TEXT_LABEL),
                                    rx.text("Create new project", font_size=F14,
                                            weight="medium", color=TEXT_LABEL),
                                    spacing="2", align="center",
                                ),
                                on_click=LumeState.open_create_dialog,
                                padding="14px 16px",
                                background=PILL_DEFAULT,
                                border_radius=R8, cursor="pointer",
                                _hover={"background": ACTIVE},
                                transition="all 150ms ease", width="100%",
                            ),
                            spacing="2", width="100%",
                        ),
                        flex="1", width="100%",
                    ),
                    spacing="3", height="100%", width="100%", padding=SP20,
                ),
                width="440px", height="100%",
                background=RIGHT_BG, box_shadow=SHADOW_RIGHT,
                z_index="201",
                on_click=rx.stop_propagation,
            ),
            position="fixed", inset="0", top="64px",
            background="rgba(80,40,120,0.25)",
            backdrop_filter="blur(4px)",
            z_index="200",
            on_click=LumeState.close_projects_panel,
            display="flex",
        ),
        rx.fragment(),
    )


def create_project_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(rx.fragment()),
        rx.dialog.content(
            rx.dialog.title(
                rx.text("New Project", font_size=F20, weight="bold", color=TEXT_HEAD),
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
                    rx.box(rx.text(LumeState.form_error, font_size=F13, color=CORAL),
                           background="rgba(240,40,128,0.08)",
                           border_radius=R8, padding="10px 14px", width="100%"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.box(
                            rx.text("Cancel", font_size=F14, weight="medium",
                                    color=TEXT_BODY),
                            on_click=LumeState.close_create_dialog,
                            background="transparent",
                            border_radius=R8, padding="0 20px", height="38px",
                            cursor="pointer", display="flex", align_items="center",
                            _hover={"background": ACTIVE},
                        ),
                    ),
                    rx.box(
                        rx.cond(
                            LumeState.creating_project,
                            rx.hstack(rx.spinner(size="2"),
                                      rx.text("Creating…", color=WHITE, font_size=F14),
                                      spacing="2", align="center"),
                            rx.text("Create project", font_size=F14, weight="medium",
                                    color=WHITE),
                        ),
                        on_click=LumeState.submit_create_project,
                        background=rx.cond(LumeState.creating_project,
                                           "rgba(160,216,48,0.5)", BTN_LIBRARIAN),
                        border="none", border_radius=R9, padding="0 20px", height="38px",
                        cursor=rx.cond(LumeState.creating_project, "not-allowed", "pointer"),
                        display="flex", align_items="center",
                    ),
                    justify="end", spacing="2", width="100%",
                ),
                spacing="4", width="100%", padding_top="8px",
            ),
            background=CARD_BG, box_shadow=SHADOW_CARD,
            max_width="480px", padding="24px", border_radius="16px",
        ),
        open=LumeState.show_create_dialog,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCORE BAR + CLIP DETAIL DRAWER
# ─────────────────────────────────────────────────────────────────────────────

def _score_bar(label: str, value: rx.Var, color: str = PURPLE) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(label, font_size=F13, color=TEXT_LABEL, width="80px", flex_shrink="0"),
            rx.box(
                rx.box(
                    height="100%", border_radius=R99,
                    background=color,
                    width=rx.cond(value >= 0, (value / 10 * 100).to_string() + "%", "0%"),
                    transition="width 400ms ease",
                ),
                height="6px", border_radius=R99,
                background="rgba(160,80,220,0.15)",
                flex="1", overflow="hidden",
            ),
            rx.text(value.to_string(), font_size=F13, weight="bold", color=TEXT_HEAD,
                    width="32px", text_align="right", flex_shrink="0"),
            spacing="2", align="center", width="100%",
        ),
        spacing="0", width="100%",
    )


def clip_detail_drawer() -> rx.Component:
    clip = LumeState.detail_clip
    score_col = rx.cond(
        clip.score >= 8.5, SCORE_HIGH,
        rx.cond(clip.score >= 6.0, SCORE_MID, SCORE_LOW)
    )

    return rx.cond(
        LumeState.show_clip_detail,
        rx.box(
            rx.box(
                rx.vstack(
                    # Header
                    rx.hstack(
                        rx.vstack(
                            rx.text(clip.filename, font_size=F17, weight="bold",
                                    color=TEXT_HEAD, overflow_wrap="anywhere"),
                            rx.text(clip.duration.to_string() + "s",
                                    font_size=F13, color=TEXT_LABEL),
                            spacing="0", align="start", flex="1", min_width="0",
                        ),
                        rx.box(
                            rx.icon("x", size=14, color=TEXT_BODY),
                            on_click=LumeState.close_clip_detail,
                            background=ACTIVE, border_radius=R6, padding="6px 8px",
                            cursor="pointer", _hover={"background": PILL_DEFAULT},
                            flex_shrink="0",
                        ),
                        width="100%", align="start", spacing="2",
                    ),
                    # Keyframes
                    rx.cond(
                        LumeState.selected_clip_frames.length() > 0,
                        rx.box(
                            rx.hstack(
                                rx.foreach(
                                    LumeState.selected_clip_frames,
                                    lambda key: rx.image(
                                        src=rx.get_upload_url(key),
                                        height="72px", aspect_ratio="16/9",
                                        object_fit="cover", border_radius=R6,
                                        flex_shrink="0",
                                    ),
                                ),
                                spacing="2",
                            ),
                            overflow_x="auto", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    rx.box(height="1px", background="rgba(160,80,220,0.15)", width="100%"),
                    # Score breakdown
                    rx.cond(
                        clip.score >= 0,
                        rx.vstack(
                            rx.hstack(
                                rx.text("Score", font_size=F15, weight="bold", color=TEXT_HEAD),
                                rx.spacer(),
                                rx.box(
                                    rx.text(clip.score.to_string(), font_size=F20,
                                            weight="bold", color=WHITE),
                                    background=score_col, border_radius=R99,
                                    padding="4px 14px",
                                ),
                                align="center", width="100%",
                            ),
                            _score_bar("Stability", clip.stability, BADGE_SCOUT),
                            _score_bar("Focus",     clip.focus,     BADGE_COLORIST),
                            _score_bar("Lighting",  clip.lighting,  BADGE_ARCHITECT),
                            spacing="2", width="100%",
                        ),
                        rx.text("Not yet scored — run Scout to analyse.",
                                font_size=F13, color=TEXT_IDLE),
                    ),
                    rx.box(height="1px", background="rgba(160,80,220,0.15)", width="100%"),
                    # Tags
                    rx.cond(
                        clip.tags.length() > 0,
                        rx.vstack(
                            rx.text("Tags", font_size=F14, weight="medium", color=TEXT_HEAD),
                            rx.hstack(
                                rx.foreach(
                                    clip.tags,
                                    lambda t: rx.box(
                                        rx.text(t, font_size=F12, color=PURPLE,
                                                weight="medium"),
                                        background="rgba(160,80,220,0.10)",
                                        border_radius=R99, padding="3px 10px",
                                    ),
                                ),
                                flex_wrap="wrap", spacing="1",
                            ),
                            spacing="2", width="100%",
                        ),
                        rx.fragment(),
                    ),
                    # Actions
                    rx.hstack(
                        rx.cond(
                            clip.is_favorite,
                            rx.box(
                                rx.text("★ Favorited", font_size=F13, weight="medium",
                                        color=AMBER),
                                on_click=LumeState.toggle_favorite(clip.clip_id),
                                background="rgba(240,160,32,0.12)",
                                border_radius=R8, padding="8px 14px", cursor="pointer",
                            ),
                            rx.box(
                                rx.text("☆ Favorite", font_size=F13, weight="medium",
                                        color=TEXT_BODY),
                                on_click=LumeState.toggle_favorite(clip.clip_id),
                                background=ACTIVE, border_radius=R8,
                                padding="8px 14px", cursor="pointer",
                                _hover={"background": PILL_DEFAULT},
                            ),
                        ),
                        rx.spacer(),
                        _btn("Re-score", bg=BTN_SCOUT,
                             on_click=LumeState.run_scout,
                             disabled=LumeState.scout_running | ~LumeState.has_project,
                             font_size=F13),
                        align="center", width="100%",
                    ),
                    spacing="4", padding=f"{SP24} 56px", width="100%",
                    overflow_y="auto",
                ),
                width="360px",
                background=RIGHT_BG,
                box_shadow="-4px 0 24px rgba(100,40,180,0.12)",
                position="absolute", top="0", right="0", bottom="0",
                z_index="201",
                on_click=rx.stop_propagation,
            ),
            position="fixed",
            top="64px", right="0", bottom="0", left="0",
            z_index="200",
            on_click=LumeState.close_clip_detail,
        ),
        rx.fragment(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ARCHITECT PREVIEW MODAL
# ─────────────────────────────────────────────────────────────────────────────

def architect_preview_modal() -> rx.Component:
    return rx.cond(
        LumeState.show_architect_preview,
        rx.box(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.vstack(
                            rx.text("Architect Preview", font_size=F20, weight="bold",
                                    color=TEXT_HEAD),
                            rx.text(
                                "Top-scored clips the Architect will assemble",
                                font_size=F12, color=TEXT_LABEL,
                            ),
                            spacing="0",
                        ),
                        rx.spacer(),
                        rx.box(
                            rx.icon("x", size=14, color=TEXT_BODY),
                            on_click=LumeState.close_architect_preview,
                            background=ACTIVE, border_radius=R6, padding="6px 8px",
                            cursor="pointer",
                        ),
                        width="100%", align="center",
                    ),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                LumeState.architect_preview_clips,
                                lambda clip: rx.hstack(
                                    rx.cond(
                                        clip.hero_frame != "",
                                        rx.image(
                                            src=rx.get_upload_url(clip.hero_frame),
                                            width="80px", height="45px",
                                            object_fit="cover", border_radius=R6,
                                            flex_shrink="0",
                                        ),
                                        rx.box(
                                            width="80px", height="45px",
                                            background=ACTIVE, border_radius=R6,
                                            flex_shrink="0",
                                        ),
                                    ),
                                    rx.vstack(
                                        rx.text(clip.filename, font_size=F13,
                                                weight="medium", color=TEXT_HEAD,
                                                overflow="hidden",
                                                text_overflow="ellipsis",
                                                white_space="nowrap"),
                                        rx.text(clip.duration.to_string() + "s",
                                                font_size=F12, color=TEXT_LABEL),
                                        spacing="0", align="start",
                                        flex="1", min_width="0",
                                    ),
                                    rx.box(
                                        rx.text(clip.score.to_string(),
                                                font_size=F13, weight="bold", color=WHITE),
                                        background=rx.cond(
                                            clip.score >= 8.5, SCORE_HIGH,
                                            rx.cond(clip.score >= 6.0, SCORE_MID, SCORE_LOW)
                                        ),
                                        border_radius=R99, padding="2px 8px",
                                        flex_shrink="0",
                                    ),
                                    spacing="3", align="center", width="100%",
                                    padding=f"{SP8} 0",
                                ),
                            ),
                            spacing="0", width="100%", padding="0 4px",
                            divide_y="1px solid rgba(160,80,220,0.10)",
                        ),
                        height="400px", width="100%",
                    ),
                    rx.hstack(
                        _btn("Run Architect", bg=BTN_ARCHITECT,
                             on_click=LumeState.run_architect,
                             disabled=LumeState.architect_running | ~LumeState.architect_enabled),
                        rx.box(
                            rx.text("Cancel", font_size=F14, weight="medium", color=TEXT_BODY),
                            on_click=LumeState.close_architect_preview,
                            background=ACTIVE, border_radius=R8,
                            padding="0 20px", height="36px",
                            cursor="pointer", display="flex", align_items="center",
                            _hover={"background": PILL_DEFAULT},
                        ),
                        spacing="2", justify="end", width="100%",
                    ),
                    spacing="4", padding=f"{SP24} 56px", width="100%",
                ),
                width="520px", max_height="600px",
                background=RIGHT_BG, border_radius="16px",
                box_shadow="0 24px 80px rgba(80,20,160,0.25)",
                on_click=rx.stop_propagation,
            ),
            position="fixed", inset="0",
            background="rgba(80,40,120,0.30)",
            backdrop_filter="blur(4px)",
            z_index="200",
            display="flex",
            align_items="center",
            justify_content="center",
            on_click=LumeState.close_architect_preview,
        ),
        rx.fragment(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SETTINGS PANEL
# ─────────────────────────────────────────────────────────────────────────────

def settings_panel() -> rx.Component:
    return rx.cond(
        LumeState.show_settings_panel,
        rx.box(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.vstack(
                            rx.text("Settings", font_size=F20, weight="bold", color=TEXT_HEAD),
                            rx.text("API keys are saved to ~/.lume/config.toml",
                                    font_size=F12, color=TEXT_LABEL),
                            spacing="0", align="start",
                        ),
                        rx.spacer(),
                        rx.box(
                            rx.icon("x", size=14, color=TEXT_BODY),
                            on_click=LumeState.close_settings,
                            background=ACTIVE, border_radius=R6, padding="6px 8px",
                            cursor="pointer", _hover={"background": PILL_DEFAULT},
                        ),
                        width="100%", align="center",
                    ),
                    rx.box(height="1px", background="rgba(160,80,220,0.15)", width="100%"),
                    _form_field("Gemini API Key", "AIzaSy...",
                                LumeState.settings_gemini_key,
                                LumeState.set_settings_gemini_key,
                                input_type="password"),
                    _form_field("Freesound API Key (optional)", "Your Freesound key",
                                LumeState.settings_freesound_key,
                                LumeState.set_settings_freesound_key,
                                input_type="password"),
                    rx.hstack(
                        rx.cond(
                            LumeState.settings_saved,
                            rx.hstack(
                                rx.icon("check", size=14, color=GREEN),
                                rx.text("Saved!", font_size=F13, color=GREEN, weight="medium"),
                                spacing="1", align="center",
                            ),
                            rx.fragment(),
                        ),
                        rx.spacer(),
                        _btn("Save", bg=GRAD_EXPORT, on_click=LumeState.save_settings),
                        align="center", width="100%",
                    ),
                    spacing="4", padding=f"{SP24} 56px", width="100%",
                ),
                width="400px",
                background=RIGHT_BG, box_shadow=SHADOW_RIGHT,
                border_radius="0 0 0 16px",
                position="absolute", top="0", right="0",
                z_index="201",
                on_click=rx.stop_propagation,
            ),
            position="fixed", inset="0", top="64px",
            background="rgba(80,40,120,0.20)",
            backdrop_filter="blur(3px)",
            z_index="200",
            on_click=LumeState.close_settings,
            display="flex",
            justify_content="flex-end",
        ),
        rx.fragment(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# BOTTOM ACTIVITY PANEL
# ─────────────────────────────────────────────────────────────────────────────

def bottom_activity_panel() -> rx.Component:
    """Collapsible bottom strip — shows agent logs."""

    # Collapsed bar — always visible, shows last message + toggle
    collapsed_bar = rx.hstack(
        rx.cond(
            LumeState.any_agent_running,
            rx.hstack(
                rx.box(
                    width="7px", height="7px", border_radius="50%",
                    background=PURPLE,
                    style={"animation": "pulse 1.2s ease-in-out infinite"},
                ),
                rx.text("Running…", font_size=F12, weight="medium", color=PURPLE),
                spacing="1", align="center", flex_shrink="0",
            ),
            rx.icon("terminal", size=13, color=TEXT_IDLE),
        ),
        rx.text(
            rx.cond(LumeState.last_log_message != "",
                    LumeState.last_log_message,
                    "Activity log"),
            font_size=F12, color=TEXT_LABEL,
            overflow="hidden", text_overflow="ellipsis", white_space="nowrap",
            flex="1", min_width="0",
        ),
        rx.box(
            rx.icon(
                rx.cond(LumeState.activity_panel_open, "chevron-down", "chevron-up"),
                size=14, color=TEXT_LABEL,
            ),
            on_click=LumeState.toggle_activity_panel,
            cursor="pointer", padding="2px 6px", border_radius=R6,
            _hover={"background": ACTIVE},
            flex_shrink="0",
        ),
        spacing="2", align="center",
        width="100%", padding=f"0 {SP16}",
        height="36px",
        background=LEFT_BG,
        border_top=f"1px solid rgba(160,80,220,0.12)",
        cursor="pointer",
        on_click=LumeState.toggle_activity_panel,
        flex_shrink="0",
    )

    # Expanded log area
    expanded_log = rx.vstack(
        # Header row
        rx.hstack(
            rx.text("Logs", font_size=F15, weight="bold", color=TEXT_HEAD),
            rx.spacer(),
            rx.box(
                rx.icon("x", size=13, color=TEXT_LABEL),
                on_click=LumeState.toggle_activity_panel,
                cursor="pointer", padding="2px 6px", border_radius=R6,
                _hover={"background": ACTIVE},
            ),
            align="center", width="100%",
            padding=f"{SP12} {SP24} {SP8}",
            flex_shrink="0",
        ),
        thought_stream(),
        spacing="0",
        height="260px",
        width="100%",
        background=PAGE,
        border_top=f"1px solid rgba(160,80,220,0.12)",
        flex_shrink="0",
        overflow="hidden",
    )

    return rx.vstack(
        rx.cond(LumeState.activity_panel_open, expanded_log, rx.fragment()),
        collapsed_bar,
        spacing="0", width="100%", flex_shrink="0",
    )


# ─────────────────────────────────────────────────────────────────────────────
# ROOT LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

def app_layout() -> rx.Component:
    kb_script = rx.html("""
<script>
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'f' || e.key === 'F') {
    // Favorite selected clip — fire Reflex event
    const evt = new CustomEvent('lume:favorite');
    window.dispatchEvent(evt);
  }
  if (e.key === 'Escape') {
    const esc = new CustomEvent('lume:escape');
    window.dispatchEvent(esc);
  }
});

// ── Log auto-scroll ──────────────────────────────────────────────────────────
function _lumeSetupLogScroll() {
  var sa = document.getElementById('log-scroll-area');
  if (!sa) { setTimeout(_lumeSetupLogScroll, 600); return; }
  var vp = sa.querySelector('[data-radix-scroll-area-viewport]');
  if (!vp) { setTimeout(_lumeSetupLogScroll, 600); return; }
  vp.scrollTop = vp.scrollHeight;
  var obs = new MutationObserver(function() {
    vp.scrollTop = vp.scrollHeight;
  });
  obs.observe(vp, { childList: true, subtree: true });
}
setTimeout(_lumeSetupLogScroll, 1000);
</script>
""")

    return rx.vstack(
        # Global CSS keyframes + Google Fonts
        rx.html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400&display=swap');
* { box-sizing: border-box; }
body { background: linear-gradient(145deg,#f0ebff 0%,#f8f0ff 50%,#fdeeff 100%); }
.lume-logo {
  font-size: 20px; font-weight: 800;
  background: linear-gradient(135deg,#7030c8,#d040a0);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.7); }
}
@keyframes progress-run {
  0%   { width: 0%; margin-left: 0%; }
  50%  { width: 60%; margin-left: 20%; }
  100% { width: 0%; margin-left: 100%; }
}
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(160,80,220,0.08); border-radius: 3px; }
::-webkit-scrollbar-thumb { background: rgba(160,80,220,0.45); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(160,80,220,0.70); }
</style>
"""),
        header(),
        rx.hstack(
            library_panel(),
            rx.vstack(
                center_panel(),
                bottom_activity_panel(),
                spacing="0",
                flex="1",
                min_width="0",
                min_height="0",
                overflow="hidden",
            ),
            version_timeline(),
            flex="1", width="100%", min_height="0", overflow="hidden", spacing="0",
            align="stretch",
        ),
        projects_panel(),
        create_project_dialog(),
        settings_panel(),
        architect_preview_modal(),
        kb_script,
        spacing="0", width="100%", height="100vh", overflow="hidden",
        font_family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        background=PAGE,
    )
