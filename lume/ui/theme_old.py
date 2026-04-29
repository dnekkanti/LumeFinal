"""
Lume design tokens — light theme palette.
"""

# ── Agent / semantic colors ────────────────────────────────────────────────────
PURPLE = "#8B5CF6"   # Librarian
TEAL   = "#06B6D4"   # Scout
AMBER  = "#EC4899"   # Colorist
CORAL  = "#F97316"   # Architect
BLUE   = "#3B82F6"   # Archivist / timeline track 2
GREEN  = "#22C55E"   # synced / high score

# ── Surface / background ───────────────────────────────────────────────────────
GRAY_50  = "#F9F9FB"   # page background
GRAY_100 = "#FFFFFF"   # panels / cards
GRAY_200 = "#E5E7EB"   # borders
GRAY_400 = "#9CA3AF"   # tertiary text
GRAY_700 = "#6B7280"   # secondary text
GRAY_900 = "#111827"   # primary text (dark)

# ── Score colors ───────────────────────────────────────────────────────────────
SCORE_HIGH = "#22C55E"
SCORE_MID  = "#F59E0B"
SCORE_LOW  = "#EF4444"

# Keep old names as aliases for backward compatibility
SCORE_GREEN = "#22C55E"   # ≥ 8.5
SCORE_AMBER = "#F59E0B"   # 6–8.4
SCORE_CORAL = "#EF4444"   # < 6

# ── Layout ─────────────────────────────────────────────────────────────────────
SIDEBAR_WIDTH       = "340px"
RIGHT_SIDEBAR_WIDTH = "320px"
HEADER_HEIGHT       = "56px"

# ── Timeline track colors ─────────────────────────────────────────────────────
TRACK_1     = "#8B5CF6"
TRACK_2     = "#3B82F6"
TRACK_3     = "#06B6D4"
TRACK_AUDIO = "#EC4899"

# ── Agent lookup dicts ─────────────────────────────────────────────────────────
AGENT_COLORS: dict[str, str] = {
    "librarian": PURPLE,
    "scout":     TEAL,
    "colorist":  AMBER,
    "architect": CORAL,
    "archivist": BLUE,
}

AGENT_LABELS: dict[str, str] = {
    "librarian": "Librarian",
    "scout":     "Scout",
    "colorist":  "Colorist",
    "architect": "Architect",
    "archivist": "Archivist",
}
