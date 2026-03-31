# LOYA Note v4.0.1
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/github/license/emaldos/LOYA-Note.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/emaldos/LOYA-Note.svg)](https://github.com/emaldos/LOYA-Note/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/emaldos/LOYA-Note.svg)](https://github.com/emaldos/LOYA-Note/issues)
LOYA Note is a local desktop app for notes, commands, targets, search, backups, and a terminal-style assistant named LOYA.
Version 4 adds grouped notes, safer updates, rollback and recovery tools, recycle bin support, import preview, diagnostics, and stronger search flows.
## Requirements
- Python `>=3.10`
- Packages are installed automatically from [`Requirements.json`](Requirements.json)
- Windows: Qt 6 requires Windows 10 version 1809 or later
- Windows: Microsoft Visual C++ Redistributable x64 should be installed for PyQt6 runtime support
## Quick Start
- Windows:
```powershell
python RunNote.py
```
- Linux:
```bash
python3 RunNote.py
```
- The launcher in [`RunNote.py`](RunNote.py) creates the local virtual environment, installs packages, validates the runtime, and starts the app.
## Main Areas
### LOYA Terminal
- Terminal-style assistant with command history, tab completion, saved searches, and recent searches
- Can open pages, search notes and commands, manage targets, and run updater commands
- Update commands:
  - `update`
  - `update check`
  - `update now`
  - `update version`
  - `update logs`
  - `update rollback`
### Notes
- Rich text notes with embedded command blocks
- Stable note opening through `note_id`
- Optional note groups
- Navigate tree with folded groups and right-click create actions
- Group Manager for rename, move, ungroup, and delete-empty-group actions
### Commands
- Standalone commands and note-linked commands
- Related-note linking, previews, and grouped search results
### Targets
- Reusable placeholders such as `{IP}` and `{URL}`
- Shared across LOYA, Search, and Mini Window
### Search
- Group-aware note and command search
- Saved searches and recent searches
- Result previews with note, command, group, tags, and related metadata
### Settings
- Security, Backup, Import & Export, Tags, Update, Recycle Bin, and Diagnostics pages
## v4 Highlights
### Update, Downgrade, and Recovery
- Installed version is read from [`CurrentVersion.info`](Cores/Update/CurrentVersion.info)
- Updater state is stored in `Cores/Update/state.json`
- Only the official repository is accepted as an update source:
  - `https://github.com/emaldos/LOYA-Note`
- Update checks validate repo owner, repo name, semantic version, and package source before install
- Updates can start from:
  - `Settings > Update`
  - LOYA terminal update commands
- Before apply, LOYA creates:
  - a data backup in `Backups/`
  - a code snapshot in `Cores/Update/OldVersions/`
- Only the last 2 code snapshots are kept for rollback
- If startup or update apply fails, recovery mode can open from the launcher, fatal startup path, or LOYA `update rollback`
### Recycle Bin
- Deleted notes, standalone commands, and targets are soft-deleted first
- Recycle-bin retention is 30 days before purge
### Import Preview
- Imports for notes, commands, targets, and target values run a dry-run preview before write
- Duplicate rows can be skipped or replaced before apply
### Diagnostics
- Settings > Diagnostics shows version, database status, update state, recycle-bin status, backups, launch state, and log shortcuts
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
Do not include local runtime folders in the release asset:
- `Data/`
- `Logs/`
- `Backups/`
- `.venv_windows/`
- `.venv_linux/`
- `Cores/Update/OldVersions/`
- `Cores/Update/state.json`
## LOYA Command Summary
- `help` or `help <command>`
- `clear`
- `history`
- `clear history`
- `reset`
- `open notes|commands|targets|settings`
- `use target "Name"`
- `add target "Name"`
- `select target "Name" { KEY="VALUE" }`
- `add KEY="VALUE"`
- `add element KEY PRIORITY`
- `search in <notes|commands|targets|targets value> for <filters>`
- `more`
- `show <id>`
- `save search <name>`
- `run search <name>`
- `update`
- `update check`
- `update now`
- `update version`
- `update logs`
- `update rollback`
## Runtime Paths
- Database: `Data/Note_LOYA_V1.db`
- Notes metadata: `Data/notes_meta.json`
- Settings: `Data/settings.json`
- Targets: `Data/Targets.json`
- Target keys: `Data/target_values.json`
- LOYA history: `Data/LOYA_Chat_history.json`
- LOYA saved searches: `Data/LOYA_Chat_saved_searches.json`
- LOYA recent searches: `Data/LOYA_Chat_recent_searches.json`
- Backups: `Backups/`
- Logs: `Logs/`
- Update runtime: `Cores/Update/`
- Code snapshots: `Cores/Update/OldVersions/`
## Versioning
- Visible app version, launcher version, updater version, and README version should stay aligned
- This build is `4.0.1`
## Links
- Repository: https://github.com/emaldos/LOYA-Note
- Issues: https://github.com/emaldos/LOYA-Note/issues
- License: https://github.com/emaldos/LOYA-Note/blob/main/LICENSE
