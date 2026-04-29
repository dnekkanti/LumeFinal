"""
Project creation and lifecycle management for Lume.

`create_project` is the single entry point called from the UI.
It validates inputs, writes the DB, initialises the Git repo via Archivist,
and registers the project in ~/.lume/config.toml.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lume.config import (
    get_github_pat,
    register_project,
    set_github_pat,
)
from lume.db.models import create_db, get_engine
from lume.git_utils.archivist import (
    Archivist,
    get_or_create_archivist,
    detect_gh_cli_auth,
    validate_github_remote,
)

logger = logging.getLogger(__name__)

PROJECTS_ROOT = Path.home() / "lume-projects"


@dataclass
class ProjectConfig:
    name: str
    source_directory: str
    remote_url: str
    github_pat: Optional[str]
    project_dir: Path
    db_path: Path


class ProjectCreationError(Exception):
    """Raised when project creation fails for a user-fixable reason."""


def create_project(
    name: str,
    source_directory: str,
    remote_url: str,
    github_pat: Optional[str] = None,
    projects_root: Optional[Path] = None,
) -> ProjectConfig:
    """
    Full project creation flow (Phase 1):

    1. Validate name and source directory.
    2. Resolve / validate GitHub credentials.
    3. Create project directory structure.
    4. Initialise SQLite DB (full schema).
    5. Initialise Git repo + .gitignore via Archivist.
    6. Register project in ~/.lume/config.toml.
    7. Return a ProjectConfig for the UI to hold.

    Raises ProjectCreationError with a human-readable message on any failure.
    """

    # ── 1. Input validation ───────────────────────────────────────────────────
    name = name.strip()
    if not name:
        raise ProjectCreationError("Project name cannot be empty.")
    if any(c in name for c in r'\/:*?"<>|'):
        raise ProjectCreationError("Project name contains invalid characters.")

    source_dir = Path(source_directory).expanduser().resolve()
    if not source_dir.exists():
        raise ProjectCreationError(f"Source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise ProjectCreationError(f"Source path is not a directory: {source_dir}")

    if not remote_url or not remote_url.startswith("https://github.com/"):
        raise ProjectCreationError(
            "A valid GitHub HTTPS remote URL is required (e.g. https://github.com/user/repo)."
        )

    # ── 2. GitHub auth ────────────────────────────────────────────────────────
    pat = github_pat or get_github_pat()

    if not pat:
        # Fall back to gh CLI session
        gh_user = detect_gh_cli_auth()
        if not gh_user:
            raise ProjectCreationError(
                "No GitHub credentials found. "
                "Provide a personal access token or run `gh auth login` first."
            )
        logger.info("Using gh CLI authenticated session")
        pat = None  # Archivist will use SSH/gh-credential-helper path

    if pat:
        ok, msg = validate_github_remote(remote_url, pat)
        if not ok:
            raise ProjectCreationError(f"GitHub validation failed: {msg}")
        # Persist PAT for future sessions
        set_github_pat(pat)
        logger.info("GitHub remote validated: %s", remote_url)

    # ── 3. Directory structure ────────────────────────────────────────────────
    root = (projects_root or PROJECTS_ROOT).expanduser().resolve()
    project_dir = root / name
    try:
        project_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ProjectCreationError(
            f"A project named '{name}' already exists at {project_dir}."
        )

    # Create subdirectories used by agents
    for sub in ("luts", "proxies", "hero_frames", "exports"):
        (project_dir / sub).mkdir()

    # ── 4. SQLite database ────────────────────────────────────────────────────
    db_path = project_dir / "lume.db"
    engine = create_db(str(db_path))
    logger.info("Created SQLite database at %s", db_path)

    # ── 5. Git init ───────────────────────────────────────────────────────────
    archivist = get_or_create_archivist(
        project_dir=project_dir,
        db_engine=engine,
        remote_url=remote_url,
        github_pat=pat,
    )
    try:
        archivist.init_repo()
    except Exception as exc:
        raise ProjectCreationError(f"Git initialisation failed: {exc}") from exc

    # Semantic commit for project creation (push worker already started by registry)
    archivist.commit(
        f"INIT: Created Lume project '{name}'",
        paths=[".gitignore", "lume.db"],
    )

    # ── 6. Register in config ─────────────────────────────────────────────────
    register_project(name=name, path=str(project_dir), remote=remote_url, source_directory=str(source_dir))
    logger.info("Project '%s' registered in ~/.lume/config.toml", name)

    return ProjectConfig(
        name=name,
        source_directory=str(source_dir),
        remote_url=remote_url,
        github_pat=pat,
        project_dir=project_dir,
        db_path=db_path,
    )


def load_project(name: str) -> Optional[ProjectConfig]:
    """
    Reload an existing project by name from ~/.lume/config.toml.
    Returns None if not found.
    """
    from lume.config import list_projects

    for p in list_projects():
        if p["name"] == name:
            project_dir = Path(p["path"])
            db_path = project_dir / "lume.db"
            if not db_path.exists():
                logger.warning("DB missing for project '%s'", name)
                return None
            return ProjectConfig(
                name=name,
                source_directory=p.get("source_directory", ""),
                remote_url=p["remote"],
                github_pat=get_github_pat(),
                project_dir=project_dir,
                db_path=db_path,
            )
    return None
