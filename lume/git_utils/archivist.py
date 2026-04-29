"""
Archivist — Git integration for Lume.

Responsibilities:
  - Initialize a Git repo for a new project
  - Write the spec-defined .gitignore
  - Validate / set the GitHub remote
  - Make semantic local commits after every agent action
  - Persistent push queue with retry logic per project (Phase 6)

Phase 6 additions:
  - Archivist now takes a SQLAlchemy *engine* instead of a session, creating
    short-lived sessions on demand so the instance can safely live for the
    entire app process.
  - Module-level `get_or_create_archivist()` returns a singleton per project
    directory so the push queue is never reset between commits.
"""

from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import git
from git import Repo, InvalidGitRepositoryError, GitCommandError
from sqlalchemy.orm import Session

from lume.db.models import GitCommit

logger = logging.getLogger(__name__)

# Files the spec says to track — everything else is ignored
GITIGNORE_CONTENT = """\
# Lume .gitignore — generated automatically, do not edit manually.
# Raw media
*.mov
*.mp4
*.mxf
*.r3d

# Proxy / cache directories
proxies/
cache/
hero_frames/
*.proxy.*

# OS noise
.DS_Store
__pycache__/
*.pyc
*.pyo
.env

# Tracked by Lume: *.fcpxml, lume.db, luts/*.cube
"""

# ── Persistent registry (one Archivist per project dir, for the process lifetime)

_archivist_registry: dict[str, "Archivist"] = {}
_registry_lock = threading.Lock()


def get_or_create_archivist(
    project_dir: str | Path,
    db_engine,
    remote_url: Optional[str] = None,
    github_pat: Optional[str] = None,
) -> "Archivist":
    """
    Return (and if needed create + start) the singleton Archivist for
    *project_dir*.  The push-worker thread is started exactly once per
    project so the queue persists across multiple commits.
    """
    key = str(Path(project_dir).resolve())
    with _registry_lock:
        if key not in _archivist_registry:
            arch = Archivist(
                project_dir=project_dir,
                db_engine=db_engine,
                remote_url=remote_url,
                github_pat=github_pat,
            )
            arch.start_push_worker()
            _archivist_registry[key] = arch
            logger.info("Archivist registered for %s", key)
        else:
            arch = _archivist_registry[key]
            # Refresh credentials in case they were set after first creation
            if remote_url:
                arch.remote_url = remote_url
            if github_pat:
                arch.github_pat = github_pat
        return arch


class Archivist:
    """
    Manages the Git lifecycle for a single Lume project directory.

    Thread-safe: all mutating Git operations are serialised through an
    internal lock.  Push retries run on a daemon thread so they never
    block the UI or other agents.

    Accepts a SQLAlchemy *engine* (not a session) so it can create
    short-lived sessions on demand — safe to hold as a long-lived singleton.
    """

    _MAX_RETRY = 5
    _RETRY_DELAY_BASE = 2  # seconds — exponential back-off

    def __init__(
        self,
        project_dir: str | Path,
        db_engine=None,
        remote_url: Optional[str] = None,
        github_pat: Optional[str] = None,
        # Legacy kwarg kept for backward-compat with project.py that passes
        # db_session; ignored here — caller should migrate to db_engine.
        db_session=None,
    ):
        self.project_dir = Path(project_dir)
        # Accept either engine or session (project.py still passes session during init)
        if db_engine is not None:
            self.db_engine = db_engine
        elif db_session is not None:
            # Derive the engine from the session for backward compat
            self.db_engine = db_session.get_bind()
        else:
            self.db_engine = None
        self.remote_url = remote_url
        self.github_pat = github_pat
        self._lock = threading.Lock()
        self._push_queue: queue.Queue[str] = queue.Queue()
        self._push_warning: Optional[str] = None  # surfaced to UI
        self._repo: Optional[Repo] = None

    # ── Initialisation ────────────────────────────────────────────────────────

    def init_repo(self) -> Repo:
        """
        Idempotently initialise a Git repo in *project_dir*.
        Creates .gitignore, makes an initial commit, and wires the remote.
        Raises ValueError if no remote has been configured (spec requirement).
        """
        if not self.remote_url:
            raise ValueError(
                "A GitHub remote URL is required before a Lume project can proceed. "
                "Please provide a remote URL and a personal access token."
            )

        with self._lock:
            gitignore_path = self.project_dir / ".gitignore"

            try:
                repo = Repo(self.project_dir)
                logger.info("Existing Git repo found at %s", self.project_dir)
            except InvalidGitRepositoryError:
                repo = Repo.init(self.project_dir)
                logger.info("Initialised new Git repo at %s", self.project_dir)

            # Write / overwrite .gitignore (spec says write on init)
            gitignore_path.write_text(GITIGNORE_CONTENT)

            # Stage .gitignore and any tracked files already present
            repo.index.add([".gitignore"])
            # Stage lume.db if it already exists (created before init_repo call)
            db_file = self.project_dir / "lume.db"
            if db_file.exists():
                repo.index.add(["lume.db"])

            # Make initial commit only if there are staged changes.
            has_staged = (not repo.head.is_valid()) or bool(repo.index.diff("HEAD"))
            if has_staged:
                try:
                    repo.index.commit("INIT: New Lume project")
                    logger.info("Made initial commit")
                except Exception as exc:
                    logger.warning("Initial commit skipped: %s", exc)

            # Set / update remote
            self._configure_remote(repo)
            self._repo = repo
            return repo

    def _configure_remote(self, repo: Repo) -> None:
        """Add or update 'origin' to point at self.remote_url."""
        remote_url = self._authenticated_url()
        try:
            origin = repo.remote("origin")
            if origin.url != remote_url:
                origin.set_url(remote_url)
                logger.info("Updated remote origin → %s", self.remote_url)
        except ValueError:
            repo.create_remote("origin", remote_url)
            logger.info("Created remote origin → %s", self.remote_url)

    def _authenticated_url(self) -> str:
        """Embed PAT in HTTPS URL for push authentication."""
        url = self.remote_url or ""
        if self.github_pat and url.startswith("https://"):
            url = url.replace("https://", f"https://{self.github_pat}@")
        return url

    # ── Commit helpers ────────────────────────────────────────────────────────

    def commit(self, message: str, paths: Optional[list[str]] = None) -> Optional[str]:
        """
        Stage *paths* (or all tracked changes when None) and commit with *message*.
        Records the commit in git_commits table.  Enqueues a push.
        Returns the commit SHA or None if nothing to commit.
        """
        with self._lock:
            repo = self._get_repo()
            if paths:
                repo.index.add([str(p) for p in paths])
            else:
                # Stage all tracked-file changes (respects .gitignore)
                repo.git.add("--update")
                # Also stage any newly created tracked file types
                for pattern in ("*.fcpxml", "*.db", "luts/*.cube"):
                    try:
                        repo.git.add(pattern)
                    except GitCommandError:
                        pass

            if repo.head.is_valid():
                staged_files = repo.git.diff("--cached", "--name-only").strip()
                if not staged_files:
                    logger.debug("Nothing to commit for: %s", message)
                    return None

            commit_obj = repo.index.commit(message)
            sha = commit_obj.hexsha
            logger.info("Committed %s: %s", sha[:7], message)

            # Persist to DB with a short-lived session
            if self.db_engine is not None:
                with Session(self.db_engine) as session:
                    record = GitCommit(
                        sha=sha,
                        message=message,
                        pushed=0,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                    session.add(record)
                    session.commit()

            # Queue push
            self._push_queue.put(sha)
            return sha

    def _get_repo(self) -> Repo:
        if self._repo is None:
            self._repo = Repo(self.project_dir)
        return self._repo

    # ── Push queue ────────────────────────────────────────────────────────────

    def start_push_worker(self) -> None:
        """Spawn a daemon thread that drains the push queue with retry logic."""
        t = threading.Thread(target=self._push_worker, daemon=True, name="lume-push")
        t.start()
        logger.info("Push worker started")

    def _push_worker(self) -> None:
        while True:
            sha = self._push_queue.get()
            self._push_with_retry(sha)
            self._push_queue.task_done()

    def _push_with_retry(self, sha: str) -> None:
        for attempt in range(1, self._MAX_RETRY + 1):
            try:
                repo = self._get_repo()
                origin = repo.remote("origin")
                # Pull remote changes first so our push is always fast-forward.
                # This handles repos initialised on GitHub with a README.
                try:
                    origin.fetch()
                    # Only rebase if the remote branch actually exists
                    remote_refs = [r.name for r in origin.refs]
                    if any("main" in r for r in remote_refs):
                        repo.git.rebase("origin/main")
                except Exception as fetch_err:
                    logger.debug("Pre-push fetch/rebase skipped: %s", fetch_err)
                origin.push(refspec="HEAD:main", set_upstream=True)
                logger.info("Pushed %s to origin (attempt %d)", sha[:7], attempt)
                # Mark pushed in DB
                if self.db_engine is not None:
                    with Session(self.db_engine) as session:
                        record = session.query(GitCommit).filter_by(sha=sha).first()
                        if record:
                            record.pushed = 1
                            session.commit()
                self._push_warning = None
                return
            except Exception as exc:
                delay = self._RETRY_DELAY_BASE ** attempt
                self._push_warning = f"Push pending ({attempt}/{self._MAX_RETRY}): {exc}"
                logger.warning("Push failed (attempt %d/%d): %s", attempt, self._MAX_RETRY, exc)
                if attempt < self._MAX_RETRY:
                    time.sleep(delay)

        self._push_warning = "Push failed after max retries — check GitHub auth"
        logger.error("Push permanently failed for %s", sha[:7])

    @property
    def push_status(self) -> dict:
        """Return a status dict for the UI."""
        pending = self._push_queue.qsize()
        if self._push_warning and "Auth failed" in self._push_warning:
            return {"state": "auth_failed", "label": "Auth failed", "pending": pending}
        if pending > 0 or self._push_warning:
            return {"state": "pending", "label": f"Push pending ({pending})", "pending": pending}
        return {"state": "synced", "label": "Synced", "pending": 0}


# ── Standalone validation helper (used during project creation) ───────────────

def validate_github_remote(remote_url: str, pat: str) -> tuple[bool, str]:
    """
    Hit the GitHub API to confirm the PAT is valid and has push access
    to *remote_url*.  Returns (ok: bool, message: str).
    """
    import re
    import requests

    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote_url)
    if not match:
        return False, "URL does not look like a GitHub repository."

    repo_path = match.group(1)
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{repo_path}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("permissions", {}).get("push"):
                return True, "GitHub remote validated."
            return False, "PAT is valid but lacks push access to this repository."
        if resp.status_code == 401:
            return False, "GitHub PAT is invalid or expired."
        if resp.status_code == 404:
            return False, "Repository not found — check the URL and that the repo exists."
        return False, f"GitHub API returned HTTP {resp.status_code}."
    except requests.RequestException as exc:
        return False, f"Network error while validating remote: {exc}"


def detect_gh_cli_auth() -> Optional[str]:
    """
    Return the GitHub username if `gh auth status` shows an authenticated session,
    otherwise return None.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "Logged in" in result.stdout:
            for line in result.stdout.splitlines():
                if "Logged in to github.com" in line:
                    return "gh_cli"
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
