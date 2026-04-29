"""
Lume — main Reflex application entry point.
Run with: reflex run
"""

import mimetypes
from pathlib import Path

import reflex as rx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from lume.state import LumeState
from lume.ui.components2 import app_layout
from lume.ui.auth import sign_in_page
from lume.ui.theme2 import *

def index() -> rx.Component:
    return app_layout()


def login_page() -> rx.Component:
    return sign_in_page()


async def serve_media(request: Request) -> Response:
    """
    Serve arbitrary local image files for hero frames and LUT previews.
    URL pattern: /media?path=/absolute/path/to/file.jpg
    Only files inside ~/lume-projects/ are served (path traversal guard).
    """
    raw = request.query_params.get("path", "")
    if not raw:
        return Response("missing path", status_code=400)

    file_path = Path(raw).resolve()
    allowed_root = (Path.home() / "lume-projects").resolve()

    try:
        file_path.relative_to(allowed_root)
    except ValueError:
        return Response("forbidden", status_code=403)

    if not file_path.exists() or not file_path.is_file():
        return Response("not found", status_code=404)

    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(str(file_path), media_type=mime)


media_app = Starlette(routes=[Route("/media", serve_media)])

app = rx.App(
    theme=rx.theme(appearance="light", accent_color="violet", radius="medium"),
    stylesheets=["https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400&display=swap"],
    api_transformer=media_app,
)

# Main app — requires auth
app.add_page(
    index,
    route="/",
    title="Lume",
    on_load=LumeState.check_auth,
)

# Sign-in page — redirects away if already logged in
app.add_page(
    login_page,
    route="/login",
    title="Sign in · Lume",
    on_load=LumeState.check_already_logged_in,
)
