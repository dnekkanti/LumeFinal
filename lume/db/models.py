"""
SQLAlchemy ORM models for Lume.
Maps exactly to the spec schema — no extra columns, no deviation.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship


class Base(DeclarativeBase):
    pass


class Clip(Base):
    __tablename__ = "clips"

    # SHA-256 checksum of source file — stable, content-addressed PK
    id = Column(String, primary_key=True)
    source_path = Column(Text, nullable=False)
    proxy_path = Column(Text)
    duration_seconds = Column(Float)
    width = Column(Integer)   # source pixel width
    height = Column(Integer)  # source pixel height
    orientation = Column(Text, default="landscape")  # "landscape" | "portrait" | "square"
    has_people = Column(Integer, default=-1)  # -1 = unknown, 0 = no, 1 = yes
    created_at = Column(Text)  # ISO-8601 string
    usable = Column(Integer, default=1)  # 0 = rejected by FFmpeg pre-filter
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=True)
    audio_keywords = Column(Text)      # comma-separated ambient sound keywords

    hero_frames = relationship("HeroFrame", back_populates="clip", cascade="all, delete-orphan")
    score = relationship("Score", back_populates="clip", uselist=False, cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="clip", cascade="all, delete-orphan")
    lut_assignments = relationship("ClipLutAssignment", back_populates="clip", cascade="all, delete-orphan")
    scene = relationship("Scene", back_populates="clips")


class HeroFrame(Base):
    __tablename__ = "hero_frames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clip_id = Column(String, ForeignKey("clips.id"), nullable=False)
    frame_path = Column(Text, nullable=False)
    timestamp_seconds = Column(Float, nullable=False)

    clip = relationship("Clip", back_populates="hero_frames")


class Score(Base):
    __tablename__ = "scores"

    clip_id = Column(String, ForeignKey("clips.id"), primary_key=True)
    score = Column(Float)
    stability = Column(Float)
    focus = Column(Float)
    lighting = Column(Float)
    is_favorite = Column(Integer, default=0)
    peak_moment = Column(Integer, default=0)

    clip = relationship("Clip", back_populates="score")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clip_id = Column(String, ForeignKey("clips.id"), nullable=False)
    tag = Column(Text, nullable=False)

    clip = relationship("Clip", back_populates="tags")


class Lut(Base):
    __tablename__ = "luts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt = Column(Text, nullable=False)
    cube_path = Column(Text, nullable=False)
    before_frame_path = Column(Text)
    after_frame_path = Column(Text)
    created_at = Column(Text)  # ISO-8601 string

    assignments = relationship("ClipLutAssignment", back_populates="lut", cascade="all, delete-orphan")


class ClipLutAssignment(Base):
    __tablename__ = "clip_lut_assignments"

    clip_id = Column(String, ForeignKey("clips.id"), nullable=False)
    lut_id = Column(Integer, ForeignKey("luts.id"), nullable=False)

    __table_args__ = (PrimaryKeyConstraint("clip_id", "lut_id"),)

    clip = relationship("Clip", back_populates="lut_assignments")
    lut = relationship("Lut", back_populates="assignments")


class Scene(Base):
    __tablename__ = "scenes"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(Text)         # AI-generated, e.g. "Golden Hour Cliffside"
    description = Column(Text)         # 1-sentence description
    shoot_date  = Column(Text)         # "2025-07-14"
    clip_count  = Column(Integer, default=0)

    clips = relationship("Clip", back_populates="scene")


class AudioMatch(Base):
    __tablename__ = "audio_matches"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    clip_id      = Column(String, ForeignKey("clips.id"), nullable=False)
    freesound_id = Column(Integer)
    name         = Column(Text)
    preview_url  = Column(Text)    # .mp3 HQ preview
    download_url = Column(Text)    # HQ download
    duration     = Column(Float)
    license      = Column(Text)
    assigned     = Column(Integer, default=0)   # 1 = user chose this
    local_path   = Column(Text)                 # filled after download


class GitCommit(Base):
    __tablename__ = "git_commits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sha = Column(Text)
    message = Column(Text, nullable=False)
    pushed = Column(Integer, default=0)
    created_at = Column(Text)  # ISO-8601 string


def create_db(db_path: str) -> None:
    """Create all tables in the SQLite database at *db_path*."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    # Enable WAL mode for safe concurrent reads during background indexing
    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _migrate(engine) -> None:
    """
    Apply lightweight forward-only migrations so that databases created by
    earlier versions of Lume gain any new columns without losing data.
    Each ALTER TABLE is wrapped in its own try/except — SQLite raises
    OperationalError if the column already exists, which we safely ignore.
    """
    migrations = [
        # Phase 5+ columns on clips
        "ALTER TABLE clips ADD COLUMN width INTEGER",
        "ALTER TABLE clips ADD COLUMN height INTEGER",
        "ALTER TABLE clips ADD COLUMN orientation TEXT DEFAULT 'landscape'",
        "ALTER TABLE clips ADD COLUMN has_people INTEGER DEFAULT -1",
        # Phase 6+ columns on scores
        "ALTER TABLE scores ADD COLUMN peak_moment INTEGER DEFAULT 0",
        # Scout sub-scores (stability, focus, lighting)
        "ALTER TABLE scores ADD COLUMN stability REAL",
        "ALTER TABLE scores ADD COLUMN focus REAL",
        "ALTER TABLE scores ADD COLUMN lighting REAL",
        # pass1_done flag on clips (Scout resumability)
        "ALTER TABLE clips ADD COLUMN pass1_done INTEGER DEFAULT 0",
        # is_favorite on scores (if added later)
        "ALTER TABLE scores ADD COLUMN is_favorite INTEGER DEFAULT 0",
        # Scene clustering
        "CREATE TABLE IF NOT EXISTS scenes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, shoot_date TEXT, clip_count INTEGER DEFAULT 0)",
        "ALTER TABLE clips ADD COLUMN scene_id INTEGER REFERENCES scenes(id)",
        "ALTER TABLE clips ADD COLUMN audio_keywords TEXT",
        # Audio matches
        "CREATE TABLE IF NOT EXISTS audio_matches (id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT REFERENCES clips(id), freesound_id INTEGER, name TEXT, preview_url TEXT, download_url TEXT, duration REAL, license TEXT, assigned INTEGER DEFAULT 0, local_path TEXT)",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists — safe to ignore


def get_engine(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    _migrate(engine)
    return engine
