# lume/ui/theme2.py — design tokens for Lume light redesign

# ── Surfaces (light, gradient-based) ─────────────────────────────────────────
PAGE         = "linear-gradient(180deg,#EDE0F5 0%,#F7D4E8 32%,#FAD0B4 65%,#FDE8C0 100%)"
TOPBAR_BG    = "linear-gradient(90deg,#ffffff 60%,#fdf4ff 100%)"
RIGHT_BG     = "linear-gradient(180deg,#ffffff 0%,#fdf8ff 100%)"
LEFT_BG      = "rgba(255,255,255,0.6)"
CARD_BG      = "#ffffff"
ACTIVE       = "rgba(240,232,255,0.7)"   # hover state on dark surfaces

# ── Brand gradients ───────────────────────────────────────────────────────────
GRAD_BRAND   = "linear-gradient(135deg,#7030c8,#d040a0)"   # logo / active tab
GRAD_EXPORT  = "linear-gradient(135deg,#9030e8,#d040b0)"   # export button
GRAD_NEW_BTN = "linear-gradient(135deg,#f0e8ff,#fde0f8)"   # new button

# ── Agent card backgrounds ────────────────────────────────────────────────────
CARD_LIBRARIAN  = "linear-gradient(135deg,#edfad0,#d8f590)"
CARD_SCOUT      = "linear-gradient(135deg,#f0e0ff,#fdd8ff)"
CARD_COLORIST   = "linear-gradient(135deg,#fff4cc,#ffe8a0)"
CARD_ARCHITECT  = "linear-gradient(135deg,#ffe0f0,#ffc8e8)"

# ── Agent button gradients ────────────────────────────────────────────────────
BTN_LIBRARIAN  = "linear-gradient(135deg,#a0d830,#70b010)"
BTN_SCOUT      = "linear-gradient(135deg,#9030d0,#d040b0)"
BTN_COLORIST   = "linear-gradient(135deg,#f0a020,#e06010)"
BTN_ARCHITECT  = "linear-gradient(135deg,#f02880,#c010a0)"
BTN_RUN        = BTN_LIBRARIAN   # bottom run bar default

# ── Agent name text colors ────────────────────────────────────────────────────
NAME_LIBRARIAN = "#3a6010"
NAME_SCOUT     = "#5010a0"
NAME_COLORIST  = "#8a5000"
NAME_ARCHITECT = "#a00858"

# ── Agent log badge colors (same as button gradients) ────────────────────────
BADGE_LIBRARIAN = BTN_LIBRARIAN
BADGE_SCOUT     = BTN_SCOUT
BADGE_COLORIST  = BTN_COLORIST
BADGE_ARCHITECT = BTN_ARCHITECT

# ── Text scale ────────────────────────────────────────────────────────────────
TEXT_HEAD   = "#2d0f60"   # headings, section titles
TEXT_LABEL  = "#9878c8"   # secondary labels / metadata
TEXT_BODY   = "#706080"   # body / description text
TEXT_IDLE   = "#b090d8"   # idle status, placeholders
TEXT_RUN    = "#6020b8"   # running status
WHITE       = "#ffffff"

# ── Pills / filter chips ──────────────────────────────────────────────────────
PILL_DEFAULT    = "linear-gradient(135deg,#ede8ff,#fde8f8)"
PILL_ACTIVE     = "linear-gradient(135deg,#8030d0,#c040b0)"
PILL_TEXT       = "#7050a8"

# ── Badges ────────────────────────────────────────────────────────────────────
BADGE_DONE      = "linear-gradient(135deg,#a0d830,#78c010)"
BADGE_SYNCED_BG = "linear-gradient(135deg,#e8f7c8,#c8f098)"
BADGE_SYNCED_TX = "#4a7010"

# ── Shadows (replaces borders) ────────────────────────────────────────────────
SHADOW_CARD     = "0 4px 18px rgba(120,50,200,0.10)"
SHADOW_SEARCH   = "0 2px 14px rgba(140,60,200,0.10)"
SHADOW_TOPBAR   = "0 1px 0 #ede8f8"
SHADOW_RIGHT    = "-3px 0 20px rgba(120,50,200,0.06)"
SHADOW_CARD_HOV = "0 8px 24px rgba(120,50,200,0.18)"

# ── Score colors ──────────────────────────────────────────────────────────────
SCORE_HIGH = "linear-gradient(135deg,#a0d830,#78c010)"
SCORE_MID  = "linear-gradient(135deg,#f0a020,#e06010)"
SCORE_LOW  = "linear-gradient(135deg,#f02880,#c010a0)"
SCORE_HIGH_TX = "#fff"
SCORE_MID_TX  = "#fff"
SCORE_LOW_TX  = "#fff"

# ── Progress bar ──────────────────────────────────────────────────────────────
PROGRESS_TRACK = "rgba(160,80,220,0.2)"
PROGRESS_FILL  = "linear-gradient(90deg,#9030d0,#e040c0)"

# ── Spacing ───────────────────────────────────────────────────────────────────
SP4  = "4px"
SP8  = "8px"
SP12 = "12px"
SP16 = "16px"
SP20 = "20px"
SP24 = "24px"
SP32 = "32px"
SP48 = "48px"

# ── Font sizes ────────────────────────────────────────────────────────────────
F32 = "32px"
F26 = "26px"
F20 = "20px"
F18 = "18px"
F17 = "17px"
F15 = "15px"
F14 = "14px"
F13 = "13px"
F12 = "12px"
F11 = "11px"

# ── Border radius ─────────────────────────────────────────────────────────────
R6  = "6px"
R8  = "8px"
R9  = "9px"
R12 = "12px"
R20 = "20px"
R99 = "999px"

# ── Legacy aliases (keeps any old references alive) ──────────────────────────
PURPLE = "#7030c8"
TEAL   = "#a0d830"
BLUE   = "#9030d0"
AMBER  = "#f0a020"
CORAL  = "#f02880"
GREEN  = "#a0d830"
PINK   = "#d040b0"
CYAN   = "#0891B2"
PANEL  = LEFT_BG
BORDER = "transparent"
BORDER_HOVER = "transparent"
TEXT1  = TEXT_HEAD
TEXT2  = TEXT_BODY
TEXT3  = TEXT_IDLE
