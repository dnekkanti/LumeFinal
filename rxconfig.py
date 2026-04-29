import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="lume_app",
    db_url="sqlite:///reflex.db",   # Reflex internal DB — separate from lume.db
    env=rx.Env.DEV,
    disable_plugins=[SitemapPlugin],
)
