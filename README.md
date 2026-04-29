# Lume

**Agentic video editing assistant for Final Cut Pro.**

Lume runs alongside FCP on macOS and automates the operational layer of video editing — ingesting footage, scoring every clip with AI, clustering scenes, suggesting color grades, matching ambient audio, and assembling export-ready FCPXML timelines — so filmmakers can focus entirely on creative decisions.

---

## What It Does

| Agent | What It Does |
|---|---|
| **Librarian** | Ingests footage, extracts metadata via ffprobe, generates thumbnails, clusters clips into scenes by shoot date, names scenes with Gemini Vision |
| **Scout** | Scores every clip 1–10 for quality and visual interest using Gemini Vision, detects people, tags descriptive keywords |
| **Colorist** | Analyzes color palettes per clip and suggests matching LUT (.cube) files from your local library |
| **Archivist** | Git version control for the project — commits the SQLite DB and FCPXML snapshots, tracks full edit history, enables rollback |
| **Architect** | Assembles a valid Final Cut Pro FCPXML 1.11 timeline from selected clips with correct timing, structure, and transitions |
| **Audio Agent** | Extracts ambient sound keywords per clip via Gemini, searches Freesound.org for royalty-free matches, lets you preview and assign audio; assigned tracks are embedded in the FCPXML export |

Every agent streams live decision logs to the **Thought Stream** — a real-time panel in the UI showing exactly what the AI is doing and why.

---

## Tech Stack

- **Frontend/Backend:** [Reflex](https://reflex.dev) — Python-to-React framework, runs as a local web app
- **Database:** SQLite per project, stored locally alongside footage
- **AI:** Google Gemini API (`gemini-2.0-flash` / `gemini-2.5-pro`) for all vision analysis
- **Video metadata:** `ffprobe` (local, no upload required)
- **Version control:** GitPython — each project is its own git repo
- **Audio:** Freesound.org API for royalty-free ambient sound search

---

## Project Structure

```
lume_v2/
├── lume/
│   ├── agents/
│   │   ├── librarian.py      # Ingestion, metadata, scene clustering
│   │   ├── scout.py          # Clip scoring, keyword tagging, people detection
│   │   ├── colorist.py       # LUT suggestion via Gemini Vision
│   │   ├── architect.py      # FCPXML 1.11 timeline assembly
│   │   ├── audio_agent.py    # Freesound keyword extraction + audio matching
│   │   └── watcher.py        # Filesystem watcher for hot folder ingestion
│   ├── db/
│   │   └── models.py         # SQLAlchemy models: Clip, Scene, AudioMatch
│   ├── git_utils/
│   │   └── archivist.py      # GitPython-based version control
│   ├── ui/
│   │   ├── components2.py    # Main app layout and all UI components
│   │   ├── auth.py           # Login / signup pages
│   │   └── theme2.py         # Design tokens (colors, spacing, typography)
│   ├── state.py              # Reflex reactive state — all app state and event handlers
│   ├── config.py             # Config management (~/.lume/config.toml)
│   └── project.py            # Project creation and registration
└── lume_app/
    └── lume_app.py           # Reflex app entry point
```

---

## Setup

### Prerequisites

- macOS (Final Cut Pro required for FCPXML export)
- Python 3.11+
- `ffprobe` installed (`brew install ffmpeg`)
- A Google Gemini API key
- (Optional) A Freesound API key for audio matching
- (Optional) A GitHub Personal Access Token for remote git backup

### Install

```bash
git clone <your-repo-url>
cd lume_v2

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure API Keys

Lume stores config at `~/.lume/config.toml`. You can set keys via environment variables or directly in the config file:

```toml
# ~/.lume/config.toml

[gemini]
api_key = "your-google-gemini-api-key"

[anthropic]
api_key = "your-anthropic-api-key"        # optional

[github]
pat = "ghp_your-github-personal-access-token"   # optional

freesound_api_key = "your-freesound-api-key"    # optional
```

Or export as environment variables:

```bash
export GOOGLE_API_KEY="your-gemini-key"
export FREESOUND_API_KEY="your-freesound-key"
```

### Run

```bash
source .venv/bin/activate
reflex run
```

The app opens at `http://localhost:3000`.

---

## Usage

1. **Create a project** — give it a name, point it at a folder of footage
2. **Run Librarian** — ingests all clips, extracts metadata, clusters into scenes, names them with Gemini
3. **Run Scout** — scores every clip 1–10, tags keywords, detects people
4. **Browse the Library** — clips are grouped by scene; filter by score, tags, or favorites
5. **Run Colorist** — get LUT suggestions for each clip based on color palette analysis
6. **Audio Lab** — run the Audio Agent to find royalty-free ambient audio matches; preview in-browser and assign tracks
7. **Build Timeline** — select clips, run Architect to generate an FCPXML timeline
8. **Export** — open the FCPXML in Final Cut Pro; assigned audio is embedded as connected media

The **Archivist** runs automatically on export — every FCPXML is committed to the project's git history for full version control.

---

## Design Principles

**Local-first.** No footage ever leaves your machine. The SQLite database and all AI calls use file paths and sampled frames — raw video is never uploaded.

**Transparent AI.** Every agent decision is streamed live to the Thought Stream. You can see exactly which frames were sampled, what Gemini returned, and why a clip scored 8.2 instead of 6.1.

**Frontier-aware.** Lume automates what AI does well — indexing, scoring, tagging, color matching, audio search. It deliberately leaves narrative judgment, pacing, and final selection to the filmmaker.

---

## Configuration Reference

```toml
# ~/.lume/config.toml

[gemini]
api_key = ""              # Required for Librarian, Scout, Colorist, Audio Agent

[anthropic]
api_key = ""              # Optional

[github]
pat = ""                  # Optional — enables push to GitHub remote

freesound_api_key = ""    # Optional — enables Audio Lab

[[projects]]
name = "my-film"
path = "/Users/name/lume-projects/my-film"
remote = "https://github.com/user/my-film"
source_directory = "/Volumes/SSD/raw-footage"
active = true
```

---

## License

MIT
