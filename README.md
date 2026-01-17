# 🚀 LOYA Note v3.2

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/github/license/emaldos/LOYA-Note.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/emaldos/LOYA-Note.svg)](https://github.com/emaldos/LOYA-Note/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/emaldos/LOYA-Note.svg)](https://github.com/emaldos/LOYA-Note/issues)

**A Local Knowledge Base + Terminal Assistant for Notes, Commands, and Targets** 🐍✨

LOYA Note is a local desktop app that combines rich notes, a command library, target-driven workflows, and a terminal-style assistant (LOYA) in one place.

- Our main goal in this program is to upgrade your notes and commands from static to dynamic.
- For example, instead of writing ping 192.168.1.1, you can turn it into ping {IP} and {IP} will automatically be replaced with the target data you selected for testing.
- It also solves the problem of having to search back through your old notes, and it helps with several other challenges too so enjoy exploring the program.
- LOYA Tools is built to take you from basic attacks to creating your own attack language. It’s not just a tool it’s your new language to speak.

---

## 📥 Installation
- Make sure you have python 3 installed first in your system
### **Option 1: IF Linux**
```bash
python3 RunNote.py
```
### **Option 2: IF Windows**
```bash
python RunNote.py
```
- Creates a virtual environment, installs dependencies from `Requirements.json`, and launches the app.

---

## 🌟 Features

### 💬 **LOYA (Terminal)**
- Terminal-style UI with prompt `LOYA >` and case-insensitive commands.
- History navigation with Up/Down, persistent across sessions.
- Tab completion and inline suggestions for commands, targets, categories, tags, and filters.
- Ctrl+Shift+V paste, Ctrl+Shift+Plus / Ctrl+Shift+Minus zoom.
- Inline system output (gray) vs normal output (white).
- Live target status line, prompt changes to `LOYA $Target >` when a target is selected.

### 📝 **Notes**
- Rich text editor: bold/italic/underline, font size, text color, alignment, lists.
- Tables with row/column add/remove, move row up/down, merge/split cells, and tab/enter navigation.
- Image insert and drag-corner resize.
- Command boxes: structured commands embedded in notes with metadata (title, category, subcategory, tags, description).
  - Inline box shows the command only; `#` edits, `X` deletes (with confirmation).
  - Command boxes are stored and synced into the Commands table.
- Notes list with open/edit/delete.
- Shortcuts: Ctrl+S save, Ctrl+Shift+C add command box.

### 🧰 **Commands**
- Command library from:
  - Commands Notes (standalone commands)
  - Note-linked commands (from command boxes in notes)
- Search, filter, and copy commands.
- Context menu: open related note, copy note name/title/category/sub/tags/description/command and IDs.
- Command add/edit dialog.

### 🎯 **Targets**
- Manage targets with values and status.
- One-click set live target (used for command placeholder replacement).
- Set Elements: manage target keys and priority (e.g., IP, URL).
- Apply JSON to target keys.

### 🔎 **Snippets**
- Search and filter commands with live target replacement.
- Table view or Split view (categories/subcategories on the left).
- Saved searches with filters by source/category/sub/tag.
- Mini Mode button to open the mini window.

### ⚙️ **Settings & Security**
- Import/Export:
  - Full database export: `.db`, `.json`, `.zip` (CSV), `.zip` (Markdown).
  - Single note export: Markdown, Human Markdown, HTML.
  - Targets and target values import/export (JSON/CSV).
  - LOYA output format toggle (structured JSON).
- Backup: manual backup/restore, auto-backup schedule, retention controls.
- Tag Manager: rename/merge/delete tags, optional update of linked note content.
- Security: app lock (PIN), database encryption (requires `cryptography`).

### 🖥️ **Mini Window**
- Compact window with tabs: Commands, LOYA, Targets.
- Favorites in Commands list (uses `Assets/Fav.png` and `Assets/Fav_selected.png`).
- Live target selection from the Targets tab.
- Always-on-top toggle, collapse/expand, restore full app.

---

### **Dependencies**
- Python `>=3.10`
- PyQt6, PyQt6-Qt6, PyQt6-sip
- openpyxl
- cryptography (required for database encryption)

---

Once launched, try:
- `help` for LOYA command help
- `open notes` to jump to Notes
- `add target "MyTarget"` to create a target

---

## ⌨️ LOYA Terminal Commands
Commands are case-insensitive. Use `help` or `help <command>` to see details and examples.

- `help` / `help <command>`: show commands and usage.
- `clear`: clear terminal output.
- `history`: show command history (Up/Down to navigate).
- `clear history`: clear command history.
- `reset`: clear terminal, history, and selected target.
- `open notes|commands|targets|settings`: jump to pages.
- `notes`, `commands`, `targets`, `settings`: page shortcuts.
- `use target "Name"`: set live target by name.
- `add target "Name"`: create a new target.
- `select target "Name" { KEY="VALUE" }`: select target context and add values.
- `select from targets "Name"`: alias for select target.
- `add KEY="VALUE"`: add values to selected target.
- `add element KEY PRIORITY`: add a target key with priority.
- `back` / `exit`: leave target context.
- `search in <notes|commands|targets|targets value> for <filters> [limit=NUM] [| copy | export [path=...] | open <id> | use target <name>]`
- `more` / `next`: paginate the last search.
- `show <id>`: preview a result from the last search.
- `save search <name>` / `run search <name>`: saved searches.

---

## 🔍 LOYA Search Syntax

### Filters and operators
- Operators: `=` (contains), `~` (fuzzy), `!=` / `!~` (negated), `and` / `or` / `not`.
- Multi-value filter: `keyword="nmap,-sS"` (comma-separated, all must match).
- Date filters: `date_from=YYYY-MM-DD`, `date_to=YYYY-MM-DD`.
- Field presence: `has=field`, `missing=field`.
- Limit: `limit=NUM` (max 200).
- Field shortcuts by scope:
  - Notes: `n:` note_name, `c:` command_keyword, `t:` tags
  - Commands: `n:` command_title, `c:` command, `t:` tags
  - Targets: `n:` target_name, `c:` target_value, `t:` target_value

### Common examples
- `search in notes for keyword="recon" tags="nmap"`
- `search in commands for tags~"nmap" limit=5`
- `search in notes for not keyword="todo" date_from=2024-01-01`
- `search in commands for command="nmap" | copy`
- `search in commands for tags~"nmap" | export path="nmap.txt"`
- `search in commands for tags~"nmap" | open 12`
- `search in commands for tags~"nmap" | use target "Acme"`

---

## 🧩 Command Placeholders & Live Targets
- Use `{KEY}` in commands (e.g., `nmap -sV {IP}`).
- Live target values replace placeholders in Snippets, Mini Commands, and LOYA search output.
- Missing values are shown inline in LOYA search results.

---

## 📂 Data and File Locations
- Database: `Data/Note_LOYA_V1.db`
- Targets: `Data/Targets.json`
- Target keys/priorities: `Data/target_values.json`
- App settings: `Data/settings.json`
- LOYA history: `Data/LOYA_Chat_history.json`
- LOYA saved searches: `Data/LOYA_Chat_saved_searches.json`
- LOYA exports: `Data/LOYA_Chat_exports/`
- Backups: `Backups/`
- Logs: `Logs/`

---

## 🔗 Links
- 🏠 **GitHub Repository**: https://github.com/emaldos/LOYA-Note
- 🐛 **Issues**: https://github.com/emaldos/LOYA-Note/issues
- 📄 **License**: https://github.com/emaldos/LOYA-Note/blob/main/LICENSE
