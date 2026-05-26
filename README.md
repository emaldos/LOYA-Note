# LOYA Note v5.1.0
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/github/license/emaldos/LOYA-Note.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/emaldos/LOYA-Note.svg)](https://github.com/emaldos/LOYA-Note/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/emaldos/LOYA-Note.svg)](https://github.com/emaldos/LOYA-Note/issues)

LOYA Note is a local desktop app for notes, reusable commands, target placeholders, snippets, backups, import/export, update recovery, and optional local security.
Version 5.1.0 focuses on the Notes workflow: richer Create Note formatting, modeless editing, better note search, linked-note backlinks, PDF export, themed HTML export, and more flexible `{Element}` detection.
## Requirements
- Python `>=3.10`
- Packages are installed automatically from [`Requirements.json`](Requirements.json)
- Runtime packages: PyQt6 and cryptography
- Windows: Qt 6 requires Windows 10 version 1809 or later
- Windows: Microsoft Visual C++ Redistributable x64 should be installed for PyQt6 runtime support
## Quick Start
Windows:
```powershell
python RunNote.py
```
Linux:
```bash
python3 RunNote.py
```
The launcher in [`RunNote.py`](RunNote.py) creates the local virtual environment, installs packages, validates the runtime, and starts the app.
## Main Areas
### Notes
- Rich text notes with embedded command blocks
- Create Note supports text alignment, text color, highlight color, font-size controls, command picking, note linking, horizontal lines, `Ctrl+S`, and draft recovery
- Command blocks support click-to-copy from the note viewer and themed HTML exports
- Stable note opening through `note_id`
- Optional note groups with a folded Navigate tree
- Group Manager for rename, move, ungroup, and delete-empty-group actions
- Selected-note search can open from the note header or `Ctrl+F` and supports match counts plus previous/next navigation
- Linked notes show backlinks through `Linked from`
### Commands
- Standalone commands and commands linked from notes
- Right-click actions are focused on `Open Related Note` and `Copy Command`
- Command Info shows command details, related note usage, metadata, and the full command
- Editing a note-linked command warns when it is used in notes and updates the related notes after save
### Snippets
- Compact command table matching the Mini Window Commands view
- Search, Favorites, and Sort By controls
- Favorites can be sorted first, and commands can be copied quickly
- Related-note opening is available when a command belongs to a note
- Snippets refresh after note save/delete and when the Snippets tab is opened
### Targets
- Reusable placeholders such as `{IP}`, `{IPv4/Subnet}`, `{User Name}`, and `{URL Path / Login}`
- Target values are shared across Notes, Commands, Search, and Mini Window
### Mini Window
- Small command, target, and Quick Space workspace
- Commands use the same related-note picker and copy flow as the main app
- Quick Space supports autosave, manual save, and theme-matched controls
### Settings
- Security, Backup, Import & Export, Tags, Update, and Recycle Bin pages
### Security
- Optional app lock on startup
- Optional local database encryption at rest
- PIN hashing uses PBKDF2 and encryption uses the installed cryptography package
- Encryption state is checked during startup health checks
## Import & Export
- Export All creates a full data `.zip`
- Export supports Notes, Commands, Targets, and Target Values in the supported file formats
- Notes can be exported as standalone HTML or PDF
- All notes can be exported as one merged PDF with page breaks
- HTML note export uses an embedded LOYA theme, preserves alignment, and renders command blocks with text `Copy` buttons
- Import uses a preview flow before writing data
- Template provides human templates
- AI Prompt Template provides prompts that explain LOYA Note structures for AI-assisted conversion
## Update, Downgrade, and Recovery
- Installed version is read from [`CurrentVersion.info`](Cores/Update/CurrentVersion.info)
- Updater state is stored in `Cores/Update/state.json`
- Only the official repository is accepted as an update source: `https://github.com/emaldos/LOYA-Note`
- Update checks validate repo owner, repo name, semantic version, and package source before install
- Updates can start from `Settings > Update`
- Before apply, LOYA creates a data backup in `Backups/` and a code snapshot in `Cores/Update/OldVersions/`
- Only the last 2 code snapshots are kept for rollback
- If startup or update apply fails, recovery mode can open from the launcher or fatal startup path
## Recycle Bin
- Deleted notes, standalone commands, and targets are soft-deleted first
- Recycle-bin retention is 30 days before purge
## Release Publishing
The in-app updater reads the latest GitHub release, not just the latest pushed commit.
To publish a new version:
1. Bump the version everywhere it is declared:
   - [`CurrentVersion.info`](Cores/Update/CurrentVersion.info)
   - [`CurentVersion.info`](Cores/Update/CurentVersion.info)
   - [`update_helpers.py`](Cores/Update/update_helpers.py)
   - [`RunNote.py`](RunNote.py)
   - [`README.md`](README.md)
2. Commit and push the code to the official repository
3. Create a semantic version tag in the form `vX.Y.Z`
4. Create a GitHub Release from that tag
5. Upload a release `.zip` asset that contains the app code root
Recommended release asset contents:
- `Assets/`
- `Cores/`
- `LOYA_Note.py`
- `RunNote.py`
- `Requirements.json`
- `README.md`
- `LICENSE`
Do not include local runtime or retired folders in the release asset:
- `Data/`
- `Logs/`
- `Backups/`
- `.venv_windows/`
- `.venv_linux/`
- `Cores/Update/OldVersions/`
- `Cores/Update/state.json`
- `Cores/LOYA_Chat/`
## Runtime Paths
- Database: `Data/Note_LOYA_V1.db`
- Notes metadata: `Data/notes_meta.json`
- Settings: `Data/settings.json`
- Targets: `Data/Targets.json`
- Target keys: `Data/target_values.json`
- Quick Space: `Data/QuicSpace.json`
- Backups: `Backups/`
- Logs: `Logs/`
- Update runtime: `Cores/Update/`
- Code snapshots: `Cores/Update/OldVersions/`
## Versioning
- Visible app version, launcher version, updater version, and README version should stay aligned
- This build is `5.1.0`
## Links
- Repository: https://github.com/emaldos/LOYA-Note
- Issues: https://github.com/emaldos/LOYA-Note/issues
- License: https://github.com/emaldos/LOYA-Note/blob/main/LICENSE
