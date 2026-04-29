"""
lume/ui/auth.py
Beautiful sign-in page for Lume.
Default credentials: admin / lume  (change in ~/.lume/config.toml under [auth])
"""
from __future__ import annotations
import reflex as rx
from lume.state import LumeState
from lume.ui.theme2 import *


# ── Stars (x%, y%, r, opacity) ────────────────────────────────────────────────
_STARS = [
    (4,8,1.2,0.55),(9,3,0.9,0.4),(14,12,1.4,0.6),(18,6,0.8,0.35),(23,2,1.1,0.5),
    (28,9,0.7,0.4),(33,5,1.3,0.55),(38,11,0.9,0.38),(42,4,1.0,0.45),(47,8,1.5,0.6),
    (52,2,0.8,0.4),(57,13,1.1,0.5),(61,7,0.9,0.42),(65,3,1.2,0.55),(70,10,0.7,0.35),
    (74,6,1.4,0.58),(78,2,1.0,0.45),(82,14,0.8,0.4),(86,5,1.3,0.52),(90,9,0.9,0.38),
    (94,3,1.1,0.5),(97,11,0.7,0.4),(6,18,0.8,0.32),(11,22,1.2,0.48),(16,16,0.9,0.38),
    (21,25,1.0,0.42),(26,20,0.7,0.3),(31,17,1.3,0.5),(36,24,0.8,0.35),(41,19,1.1,0.45),
    (46,15,0.9,0.38),(51,22,1.4,0.52),(56,18,0.8,0.32),(60,26,1.0,0.44),(63,14,0.7,0.3),
    (67,21,1.2,0.48),(72,17,0.9,0.38),(76,24,1.1,0.46),(80,20,0.8,0.34),(84,16,1.3,0.5),
    (88,23,0.7,0.3),(92,18,1.0,0.42),(96,25,0.8,0.36),(3,29,0.9,0.3),(8,32,1.1,0.42),
    (13,27,0.8,0.32),(19,34,1.2,0.46),(24,30,0.7,0.28),(29,28,1.0,0.38),(35,33,0.9,0.34),
]

_STARS_SVG = (
    '<svg class="lume-stars" viewBox="0 0 100 100" preserveAspectRatio="none"'
    ' xmlns="http://www.w3.org/2000/svg">'
    + "".join(
        f'<circle cx="{x}" cy="{y}" r="{r * 0.12}" fill="rgba(255,240,210,{op * 0.7})"/>'
        for x, y, r, op in _STARS
    )
    + "</svg>"
)

# ── Mountain SVG paths ────────────────────────────────────────────────────────
# Three layers: distant (lightest), mid, near (richest color)
_MOUNTAINS_SVG = """
<svg class="lume-mountains" viewBox="0 0 1440 260" preserveAspectRatio="none"
     xmlns="http://www.w3.org/2000/svg">
  <!-- Distant peaks — hazy rose -->
  <path d="M0,260 L0,180 Q60,110 120,150 Q200,70 280,120 Q360,50 440,100
           Q520,30 600,80 Q680,20 760,70 Q840,40 920,90 Q1000,20 1080,65
           Q1160,30 1240,75 Q1320,45 1440,80 L1440,260 Z"
        fill="rgba(120,50,60,0.12)"/>
  <!-- Mid mountains — deeper mauve -->
  <path d="M0,260 L0,200 Q80,140 160,170 Q240,100 320,145 Q400,80 480,125
           Q560,60 640,110 Q720,50 800,100 Q880,70 960,115 Q1040,80 1120,120
           Q1200,60 1280,105 Q1360,75 1440,110 L1440,260 Z"
        fill="rgba(100,40,50,0.18)"/>
  <!-- Near hills — warm burnt sienna -->
  <path d="M0,260 L0,225 Q90,190 180,210 Q270,175 360,200 Q450,165 540,195
           Q630,170 720,198 Q810,168 900,196 Q990,175 1080,205 Q1170,172 1260,200
           Q1350,180 1440,205 L1440,260 Z"
        fill="rgba(80,30,30,0.22)"/>
  <!-- Rolling foreground hills — dark silhouette -->
  <path d="M0,260 L0,245 Q120,228 240,242 Q360,224 480,240 Q600,222 720,238
           Q840,220 960,236 Q1080,222 1200,240 Q1320,225 1440,238 L1440,260 Z"
        fill="rgba(50,20,20,0.28)"/>
</svg>
"""

# ── Pine tree treeline SVG ────────────────────────────────────────────────────
# Row of simple pine silhouettes in front of the mountains
def _tree(x: int, h: int, w: int, op: float) -> str:
    """Single pine tree: stacked triangles + trunk."""
    cx = x
    # Three layered triangles (top to bottom, each wider) — dark warm silhouette
    t1 = f'<polygon points="{cx},{260-h} {cx-w//3},{260-h//2+10} {cx+w//3},{260-h//2+10}" fill="rgba(50,25,20,{op})"/>'
    t2 = f'<polygon points="{cx},{260-h//2+15} {cx-w//2},{260-h//4+10} {cx+w//2},{260-h//4+10}" fill="rgba(50,25,20,{op})"/>'
    t3 = f'<polygon points="{cx},{260-h//4+15} {cx-w*2//3},{260} {cx+w*2//3},{260}" fill="rgba(50,25,20,{op})"/>'
    return t1 + t2 + t3

_TREE_SPECS = [
    # x,  h,   w,   opacity
    (30,  80,  28, 0.28),
    (70,  65,  24, 0.24),
    (105, 90,  32, 0.30),
    (140, 58,  22, 0.22),
    (175, 75,  28, 0.26),
    (210, 50,  20, 0.20),
    (1180, 72, 26, 0.24),
    (1220, 88, 30, 0.28),
    (1260, 60, 22, 0.22),
    (1300, 80, 28, 0.26),
    (1340, 55, 20, 0.20),
    (1380, 70, 26, 0.24),
    (1420, 50, 18, 0.18),
]

_TREES_SVG = (
    '<svg class="lume-trees" viewBox="0 0 1440 260" preserveAspectRatio="none"'
    ' xmlns="http://www.w3.org/2000/svg">'
    + "".join(_tree(x, h, w, op) for x, h, w, op in _TREE_SPECS)
    + "</svg>"
)

# ── Film strip clips ──────────────────────────────────────────────────────────
_FILM_CLIPS = [
    ("72px", "rgba(255,160,60,0.18)"),
    ("48px", "rgba(120,80,220,0.15)"),
    ("90px", "rgba(60,120,240,0.13)"),
    ("56px", "rgba(220,60,160,0.16)"),
    ("80px", "rgba(100,180,80,0.13)"),
    ("40px", "rgba(255,100,80,0.14)"),
    ("96px", "rgba(140,80,220,0.15)"),
    ("60px", "rgba(255,200,60,0.14)"),
    ("72px", "rgba(80,160,240,0.13)"),
    ("48px", "rgba(220,80,180,0.15)"),
    ("88px", "rgba(160,80,220,0.14)"),
    ("56px", "rgba(255,140,60,0.15)"),
    ("76px", "rgba(80,120,220,0.13)"),
    ("44px", "rgba(200,60,140,0.14)"),
    ("92px", "rgba(100,200,80,0.12)"),
]
_FILM_HTML = "".join(
    f'<div class="lume-film-clip" style="width:{w};background:{c};"></div>'
    for w, c in _FILM_CLIPS
)

# ── Bokeh particles (x%, y%, size, color, anim-delay, anim-dur) ──────────────
_BOKEH = [
    (8,  15, 10, "rgba(255,210,80,0.50)",  "0s",   "7s"),
    (16, 45, 6,  "rgba(180,90,255,0.45)",  "-2s",  "9s"),
    (22, 28, 8,  "rgba(255,120,80,0.42)",  "-4s",  "8s"),
    (85, 20, 7,  "rgba(255,200,80,0.48)",  "-1s",  "10s"),
    (91, 55, 5,  "rgba(160,80,255,0.42)",  "-5s",  "7s"),
    (78, 38, 9,  "rgba(255,80,180,0.40)",  "-3s",  "11s"),
    (5,  62, 5,  "rgba(130,200,80,0.38)",  "-6s",  "9s"),
    (94, 72, 6,  "rgba(80,180,255,0.40)",  "-2s",  "8s"),
    (45, 10, 4,  "rgba(255,240,80,0.50)",  "-7s",  "12s"),
    (55, 85, 7,  "rgba(220,80,200,0.38)",  "-4s",  "9s"),
    (32, 70, 5,  "rgba(100,220,120,0.38)", "-1s",  "10s"),
    (68, 15, 8,  "rgba(255,160,60,0.45)",  "-3s",  "8s"),
    (12, 80, 4,  "rgba(160,100,255,0.40)", "-5s",  "11s"),
    (88, 85, 6,  "rgba(255,100,100,0.38)", "-8s",  "13s"),
]

_BOKEH_HTML = "".join(
    f'<div class="lume-bk" style="left:{x}%;top:{y}%;width:{s}px;height:{s}px;'
    f'background:{c};box-shadow:0 0 {s*2}px {s//2}px {c};'
    f'animation-delay:{ad};animation-duration:{dur};"></div>'
    for x, y, s, c, ad, dur in _BOKEH
)

# ── Full background CSS ───────────────────────────────────────────────────────
_BG_CSS = """
/* ── Stars SVG ── */
.lume-stars {
  position: fixed; top: 0; left: 0; width: 100%; height: 55%;
  pointer-events: none; z-index: 0;
}

/* ── Ambient glow orbs ── */
.lume-orb-1 {
  position: fixed; top: -160px; right: -80px;
  width: 600px; height: 600px; border-radius: 50%;
  background: radial-gradient(circle, rgba(220,100,160,0.22) 0%, transparent 65%);
  pointer-events: none; z-index: 0;
}
.lume-orb-2 {
  position: fixed; bottom: 52px; left: -80px;
  width: 600px; height: 600px; border-radius: 50%;
  background: radial-gradient(circle, rgba(240,160,60,0.18) 0%, transparent 65%);
  pointer-events: none; z-index: 0;
}
/* Sun glow — top center warm burst */
.lume-sun {
  position: fixed; top: -80px; left: 50%;
  transform: translateX(-50%);
  width: 600px; height: 400px; border-radius: 50%;
  background: radial-gradient(circle,
    rgba(255,210,120,0.30) 0%,
    rgba(255,160,80,0.14) 45%,
    transparent 70%);
  pointer-events: none; z-index: 0;
}

/* ── Mountains ── */
.lume-mountains {
  position: fixed; bottom: 52px; left: 0; right: 0;
  height: 260px;
  pointer-events: none; z-index: 1;
}
.lume-mountains svg { width: 100%; height: 100%; }

/* ── Trees ── */
.lume-trees {
  position: fixed; bottom: 52px; left: 0; right: 0;
  height: 260px;
  pointer-events: none; z-index: 2;
}
.lume-trees svg { width: 100%; height: 100%; }

/* ── Bokeh particles ── */
.lume-bk {
  position: fixed; border-radius: 50%;
  pointer-events: none; z-index: 0;
  animation: lume-bk-float ease-in-out infinite;
}
@keyframes lume-bk-float {
  0%, 100% { transform: translateY(0) scale(1);   opacity: 1; }
  40%       { transform: translateY(-18px) scale(1.15); opacity: 0.7; }
  70%       { transform: translateY(-8px) scale(0.9);  opacity: 0.85; }
}

/* ── Floating video frames ── */
.lume-frame {
  position: fixed; border-radius: 10px;
  pointer-events: none; z-index: 3;
}
.lume-frame-1 {
  top: 40px; right: -20px;
  width: 380px; height: 214px;
  background: linear-gradient(135deg,
    rgba(255,200,80,0.16) 0%, rgba(255,100,40,0.09) 55%, rgba(180,60,220,0.07) 100%);
  border: 1.5px solid rgba(220,140,60,0.22);
  transform: rotate(6deg);
  animation: lume-frame-drift1 10s ease-in-out infinite;
  box-shadow: inset 0 0 40px rgba(255,160,40,0.05);
}
.lume-frame-1::after {
  content: '▶'; position: absolute;
  top: 50%; left: 50%; transform: translate(-50%,-50%);
  font-size: 26px; color: rgba(255,160,60,0.22); font-family: sans-serif;
}
.lume-frame-2 {
  bottom: 120px; left: -40px;
  width: 300px; height: 169px;
  background: linear-gradient(135deg,
    rgba(40,80,220,0.11) 0%, rgba(100,40,200,0.13) 55%, rgba(180,40,200,0.09) 100%);
  border: 1.5px solid rgba(100,80,220,0.20);
  transform: rotate(-7deg);
  animation: lume-frame-drift2 12s ease-in-out infinite;
}
.lume-frame-2::after {
  content: '▶'; position: absolute;
  top: 50%; left: 50%; transform: translate(-50%,-50%);
  font-size: 18px; color: rgba(120,80,220,0.20); font-family: sans-serif;
}
.lume-frame-3 {
  top: 36%; right: 2%;
  width: 190px; height: 107px;
  background: rgba(240,220,255,0.10);
  border: 1px solid rgba(180,100,220,0.16);
  transform: rotate(-4deg);
  animation: lume-frame-drift1 14s ease-in-out infinite 5s;
}
.lume-frame-4 {
  top: 18%; left: 2%;
  width: 145px; height: 82px;
  background: rgba(220,200,255,0.09);
  border: 1px solid rgba(160,100,220,0.13);
  transform: rotate(5deg);
  animation: lume-frame-drift2 13s ease-in-out infinite 2s;
}
@keyframes lume-frame-drift1 {
  0%, 100% { transform: rotate(6deg)  translateY(0px); }
  50%       { transform: rotate(6deg)  translateY(-12px); }
}
@keyframes lume-frame-drift2 {
  0%, 100% { transform: rotate(-7deg) translateY(0px); }
  50%       { transform: rotate(-7deg) translateY(-10px); }
}

/* ── Camera aperture ring ── */
.lume-aperture {
  position: fixed; top: 50%; right: -55px;
  transform: translateY(-50%);
  width: 260px; height: 260px; border-radius: 50%;
  border: 1px solid rgba(200,100,60,0.10);
  box-shadow:
    0 0 0 26px rgba(200,100,60,0.05),
    0 0 0 52px rgba(200,100,60,0.03),
    0 0 0 78px rgba(200,100,60,0.02),
    0 0 0 104px rgba(200,100,60,0.01);
  pointer-events: none; z-index: 0;
  animation: lume-spin 35s linear infinite;
}
@keyframes lume-spin {
  from { transform: translateY(-50%) rotate(0deg); }
  to   { transform: translateY(-50%) rotate(360deg); }
}

/* ── Lens flares ── */
.lume-flare {
  position: fixed; border-radius: 50%;
  pointer-events: none; z-index: 0;
  animation: lume-pulse 4s ease-in-out infinite;
}
.lume-flare-1 {
  top: 21%; right: 20%; width: 6px; height: 6px;
  background: rgba(255,220,120,0.70);
  box-shadow: 0 0 14px 5px rgba(255,190,60,0.28);
}
.lume-flare-2 {
  top: 58%; left: 17%; width: 4px; height: 4px;
  background: rgba(255,140,80,0.55);
  box-shadow: 0 0 10px 4px rgba(240,110,60,0.22);
  animation-delay: -1.5s;
}
.lume-flare-3 {
  bottom: 30%; right: 26%; width: 5px; height: 5px;
  background: rgba(240,100,140,0.50);
  box-shadow: 0 0 10px 4px rgba(220,80,120,0.20);
  animation-delay: -3s;
}
.lume-flare-4 {
  top: 10%; left: 35%; width: 3px; height: 3px;
  background: rgba(255,230,140,0.70);
  box-shadow: 0 0 8px 3px rgba(255,210,80,0.25);
  animation-delay: -0.8s;
}
@keyframes lume-pulse {
  0%, 100% { opacity: 1;    transform: scale(1); }
  50%       { opacity: 0.3; transform: scale(0.55); }
}

/* ── Film strip ── */
.lume-filmstrip {
  position: fixed; bottom: 0; left: 0; right: 0; height: 52px;
  background: rgba(80,30,20,0.08);
  border-top: 1px solid rgba(180,100,60,0.15);
  display: flex; align-items: center; padding: 0 16px;
  pointer-events: none; z-index: 4; overflow: hidden;
}
.lume-film-track { display: flex; align-items: center; flex: 1; height: 100%; }
.lume-filmstrip::before, .lume-filmstrip::after {
  content: ''; position: absolute; left: 0; right: 0; height: 10px;
  background-image: repeating-linear-gradient(
    90deg, transparent 0px, transparent 14px,
    rgba(255,255,255,0.30) 14px, rgba(255,255,255,0.30) 24px);
}
.lume-filmstrip::before { top: 4px; }
.lume-filmstrip::after  { bottom: 4px; }
.lume-film-clip { height: 28px; flex-shrink: 0; border-radius: 3px; margin: 0 2px; }

/* ── Card ── */
.lume-login-card {
  animation: lume-fadein 0.55s cubic-bezier(0.22,1,0.36,1) both;
}
@keyframes lume-fadein {
  from { opacity: 0; transform: translateY(20px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0)    scale(1); }
}
.lume-login-input { transition: box-shadow 200ms ease; }
.lume-login-input:focus-within {
  box-shadow: 0 0 0 2px rgba(200,100,60,0.40) !important;
}
"""


# ── Input field component ─────────────────────────────────────────────────────

def _input_field(
    label: str,
    placeholder: str,
    value: rx.Var,
    on_change,
    input_type: str = "text",
) -> rx.Component:
    return rx.vstack(
        rx.text(label, font_size="13px", weight="medium",
                color="rgba(150,70,40,0.90)", letter_spacing="0.02em"),
        rx.box(
            rx.input(
                placeholder=placeholder,
                value=value,
                on_change=on_change,
                type=input_type,
                on_key_up=LumeState.login_on_enter,
                background="transparent",
                border="none",
                outline="none",
                font_size="15px",
                color=TEXT_HEAD,
                font_family="Inter, sans-serif",
                padding="0",
                width="100%",
                _focus={"outline": "none", "box_shadow": "none"},
                _placeholder={"color": TEXT_IDLE},
            ),
            class_name="lume-login-input",
            background="rgba(255,240,230,0.65)",
            border_radius="10px",
            padding="12px 16px",
            width="100%",
            box_shadow="0 2px 8px rgba(180,80,40,0.08)",
        ),
        spacing="2", width="100%", align="start",
    )


# ── Page ─────────────────────────────────────────────────────────────────────

def sign_in_page() -> rx.Component:
    return rx.box(
        # ── Inject full background scene ──────────────────────────────────────
        rx.html(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
* {{ box-sizing: border-box; }}
{_BG_CSS}
</style>

<!-- Stars -->
{_STARS_SVG}

<!-- Glow layers -->
<div class="lume-orb-1"></div>
<div class="lume-orb-2"></div>
<div class="lume-sun"></div>

<!-- Bokeh / fireflies -->
{_BOKEH_HTML}

<!-- Aperture ring -->
<div class="lume-aperture"></div>

<!-- Floating video frames -->
<div class="lume-frame lume-frame-1"></div>
<div class="lume-frame lume-frame-2"></div>
<div class="lume-frame lume-frame-3"></div>
<div class="lume-frame lume-frame-4"></div>

<!-- Lens flares -->
<div class="lume-flare lume-flare-1"></div>
<div class="lume-flare lume-flare-2"></div>
<div class="lume-flare lume-flare-3"></div>
<div class="lume-flare lume-flare-4"></div>

<!-- Mountain silhouettes -->
<div class="lume-mountains">{_MOUNTAINS_SVG}</div>

<!-- Pine treeline -->
<div class="lume-trees">{_TREES_SVG}</div>

<!-- Film strip -->
<div class="lume-filmstrip">
  <div class="lume-film-track">{_FILM_HTML}{_FILM_HTML}</div>
</div>
"""),

        # ── Login card ────────────────────────────────────────────────────────
        rx.center(
            rx.box(
                rx.vstack(

                    # Logo + tagline
                    rx.vstack(
                        rx.hstack(
                            rx.html(
                                '<span style="font-size:36px;font-weight:800;'
                                'background:linear-gradient(135deg,#7030c8,#d040a0);'
                                '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
                                'background-clip:text;font-family:Inter,sans-serif;">Lume</span>'
                            ),
                            rx.box(
                                rx.html(
                                    '<span style="font-size:11px;font-weight:700;color:#fff;'
                                    'letter-spacing:0.06em;font-family:Inter,sans-serif;">AI</span>'
                                ),
                                background="linear-gradient(135deg,#7030c8,#d040a0)",
                                border_radius="6px", padding="3px 8px",
                                margin_top="4px", flex_shrink="0",
                            ),
                            spacing="2", align="center",
                        ),
                        rx.text(
                            "Your AI-powered video edit suite",
                            font_size="14px", color=TEXT_LABEL,
                            font_weight="400", text_align="center",
                        ),
                        spacing="1", align="center", width="100%",
                        padding_bottom="8px",
                    ),

                    # Divider
                    rx.box(
                        height="1px",
                        background="linear-gradient(90deg,transparent,rgba(160,80,220,0.2),transparent)",
                        width="100%", margin="4px 0 20px",
                    ),

                    # Form fields
                    rx.vstack(
                        _input_field("Username", "Enter username",
                                     LumeState.login_username,
                                     LumeState.set_login_username),
                        _input_field("Password", "Enter password",
                                     LumeState.login_password,
                                     LumeState.set_login_password,
                                     input_type="password"),
                        spacing="4", width="100%",
                    ),

                    # Error
                    rx.cond(
                        LumeState.login_error != "",
                        rx.hstack(
                            rx.icon("circle-alert", size=14, color=CORAL),
                            rx.text(LumeState.login_error,
                                    font_size="13px", color=CORAL),
                            spacing="1", align="center",
                            padding="8px 12px",
                            background="rgba(240,40,128,0.07)",
                            border_radius="8px", width="100%",
                        ),
                        rx.fragment(),
                    ),

                    # Sign in button
                    rx.box(
                        rx.hstack(
                            rx.text("Sign in", font_size="15px", weight="bold",
                                    color=WHITE),
                            rx.icon("arrow-right", size=16, color=WHITE),
                            spacing="2", align="center", justify="center",
                        ),
                        on_click=LumeState.login,
                        background="linear-gradient(135deg,#7030c8,#d040a0)",
                        border_radius="10px", height="46px", width="100%",
                        cursor="pointer", display="flex",
                        align_items="center", justify_content="center",
                        margin_top="4px",
                        box_shadow="0 4px 20px rgba(112,48,200,0.35)",
                        _hover={"filter": "brightness(1.08)",
                                "box-shadow": "0 6px 28px rgba(112,48,200,0.45)"},
                        _active={"filter": "brightness(0.95)"},
                        transition="all 180ms ease",
                    ),


                    spacing="4", width="100%",
                ),

                class_name="lume-login-card",
                background="rgba(255,255,255,0.82)",
                border_radius="24px",
                padding="48px 44px 40px",
                width="420px",
                box_shadow=(
                    "0 32px 80px rgba(180,80,60,0.18),"
                    "0 8px 24px rgba(200,100,60,0.12),"
                    "inset 0 1px 0 rgba(255,255,255,0.9)"
                ),
                style={"backdrop-filter": "blur(24px)",
                       "-webkit-backdrop-filter": "blur(24px)"},
                position="relative", z_index="10",
            ),
            height="100vh", width="100%",
        ),

        min_height="100vh",
        background="linear-gradient(180deg,#C8A0D4 0%,#E088B8 32%,#EA9470 65%,#F5C870 100%)",
        font_family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
        position="relative",
        overflow="hidden",
    )
