import os
import json
import re
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QToolButton,
    QLineEdit,
    QTabBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSizePolicy,
    QAbstractItemView,
    QApplication,
)
from Cores import SearchCore, Target
try:
    from Cores.LOYA_Chat import LOYA_Chat
except Exception:
    LOYA_Chat = None
def _abs(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)
def _data_dir():
    d = _abs("..", "Data")
    os.makedirs(d, exist_ok=True)
    return d
def _settings_path():
    return os.path.join(_data_dir(), "settings.json")
def _read_json(p, default):
    try:
        if not p or not os.path.isfile(p):
            return default
        with open(p, "r", encoding="utf-8") as f:
            v = json.load(f)
            return v if v is not None else default
    except Exception:
        return default
def _write_json(p, obj):
    t = p + ".tmp"
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(t, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(t, p)
        return True
    except Exception:
        try:
            if os.path.isfile(t):
                os.remove(t)
        except Exception:
            pass
        return False
def _read_settings():
    return _read_json(_settings_path(), {})
def _write_settings(data):
    return _write_json(_settings_path(), data or {})
def _get_mini_settings():
    d = _read_settings()
    m = d.get("mini_window", {}) if isinstance(d, dict) else {}
    favs = m.get("favorites", [])
    if not isinstance(favs, list):
        favs = []
    try:
        w = int(m.get("w", 520))
    except Exception:
        w = 520
    try:
        h = int(m.get("h", 420))
    except Exception:
        h = 420
    return {
        "x": m.get("x"),
        "y": m.get("y"),
        "w": max(320, w),
        "h": max(240, h),
        "collapsed": bool(m.get("collapsed", False)),
        "always_on_top": bool(m.get("always_on_top", False)),
        "favorites": [str(x) for x in favs if str(x).strip()],
        "favorites_only": bool(m.get("favorites_only", False)),
    }
def _save_mini_settings(cfg):
    d = _read_settings()
    if not isinstance(d, dict):
        d = {}
    cur = d.get("mini_window", {}) if isinstance(d.get("mini_window", {}), dict) else {}
    cur.update(cfg or {})
    d["mini_window"] = cur
    return _write_settings(d)
def _norm(s):
    return ("" if s is None else str(s)).strip()
def _l(s):
    return _norm(s).lower()
def _tokenize(text):
    t = _l(text)
    return [x for x in re.split(r"[,\s]+", t) if x]
def _compress_cmd(cmd):
    raw = _norm(cmd)
    if not raw:
        return ""
    lines = [ln.strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ""
    text = " ".join(lines)
    return re.sub(r"\s+", " ", text).strip()
class MiniPlaceholder(QWidget):
    def __init__(self, title, subtitle="Coming soon...", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        t = QLabel(title, self)
        t.setObjectName("PageTitle")
        s = QLabel(subtitle, self)
        s.setObjectName("PageSubTitle")
        s.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(s)
        layout.addStretch(1)
class MiniCommands(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MiniCmdFrame")
        self._db_path = None
        self._db_mtime = None
        self._notes = []
        self._favorites = set()
        self._favorites_only = False
        cfg = _get_mini_settings()
        self._favorites = set(cfg.get("favorites") or [])
        self._favorites_only = bool(cfg.get("favorites_only", False))
        self.ctx = SearchCore.LiveTargetContext()
        self.rep = SearchCore.CommandReplacer(self.ctx)
        self._fav_icon = None
        self._fav_icon_on = None
        self._load_icons()
        self._build_ui()
        QTimer.singleShot(0, self.reload)
        self.t = QTimer(self)
        self.t.setInterval(900)
        self.t.timeout.connect(self._tick)
        self.t.start()
    def _load_icons(self):
        ico_on = _abs("..", "Assets", "Fav_selected.png")
        ico_off = _abs("..", "Assets", "Fav.png")
        if os.path.isfile(ico_on):
            self._fav_icon_on = QIcon(ico_on)
        if os.path.isfile(ico_off):
            self._fav_icon = QIcon(ico_off)
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.search = QLineEdit(self)
        self.search.setObjectName("MiniSearchInput")
        self.search.setPlaceholderText("Search commands...")
        self.search.textChanged.connect(lambda _: self._apply())
        self.btn_fav = QToolButton(self)
        self.btn_fav.setObjectName("MiniFilterBtn")
        self.btn_fav.setText("Favorites")
        self.btn_fav.setCheckable(True)
        self.btn_fav.setChecked(self._favorites_only)
        self.btn_fav.clicked.connect(self._toggle_favorites_only)
        top.addWidget(self.search, 1)
        top.addWidget(self.btn_fav, 0)
        root.addLayout(top)
        self.table = QTableWidget(self)
        self.table.setObjectName("MiniCmdTable")
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Fav", "Title", "Command"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.cellClicked.connect(self._on_cell_click)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(1, 160)
        root.addWidget(self.table, 1)
        self.status = QFrame(self)
        self.status.setObjectName("MiniStatusBar")
        srow = QHBoxLayout(self.status)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(8)
        self.status_dot = QFrame(self.status)
        self.status_dot.setObjectName("MiniStatusDot")
        self.status_dot.setFixedSize(10, 10)
        self.status_text = QLabel("Live", self.status)
        self.status_text.setObjectName("MiniStatusText")
        self.status_target = QLabel("", self.status)
        self.status_target.setObjectName("MiniStatusTarget")
        srow.addWidget(self.status_dot, 0)
        srow.addWidget(self.status_text, 0)
        srow.addWidget(self.status_target, 0)
        srow.addStretch(1)
        root.addWidget(self.status, 0)
        self._update_status()
    def _cmd_key(self, item):
        if not isinstance(item, dict):
            return ""
        src = item.get("src") or ""
        cid = item.get("id")
        if cid is not None:
            return f"{src}:{cid}"
        cmd = item.get("command") or ""
        if cmd:
            return cmd.strip().lower()
        title = item.get("title") or ""
        return title.strip().lower()
    def _match(self, item, tokens):
        if not tokens:
            return True
        blob = " ".join(
            [
                item.get("title") or "",
                item.get("category") or "",
                item.get("sub") or "",
                item.get("tags") or "",
                item.get("command") or "",
                item.get("description") or "",
            ]
        )
        b = _l(blob)
        return all(t in b for t in tokens)
    def _filtered(self):
        tokens = _tokenize(self.search.text())
        base = [n for n in (self._notes or []) if self._match(n, tokens)]
        if self._favorites_only:
            return [n for n in base if self._cmd_key(n) in self._favorites]
        favs = [n for n in base if self._cmd_key(n) in self._favorites]
        rest = [n for n in base if self._cmd_key(n) not in self._favorites]
        return favs + rest
    def _render(self):
        rows = self._filtered()
        self.table.setRowCount(len(rows))
        for r, n in enumerate(rows):
            key = self._cmd_key(n)
            is_fav = key in self._favorites
            fav_item = QTableWidgetItem("")
            icon = self._fav_icon_on if is_fav else self._fav_icon
            if icon:
                fav_item.setIcon(icon)
            fav_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fav_item.setToolTip("Toggle favorite")
            title = n.get("title") or "Untitled"
            title_item = QTableWidgetItem(title)
            title_item.setData(Qt.ItemDataRole.UserRole, n)
            meta_parts = []
            cat = _norm(n.get("category"))
            sub = _norm(n.get("sub"))
            tags = _norm(n.get("tags"))
            if cat or sub:
                meta_parts.append(f"{cat or 'Uncategorized'}/{sub or 'General'}")
            if tags:
                meta_parts.append(f"tags: {tags}")
            if meta_parts:
                title_item.setToolTip(" | ".join(meta_parts))
            cmd = self._preview_cmd(n)
            compact = _compress_cmd(cmd)
            cmd_item = QTableWidgetItem(compact)
            cmd_item.setToolTip(cmd)
            cmd_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r, 0, fav_item)
            self.table.setItem(r, 1, title_item)
            self.table.setItem(r, 2, cmd_item)
            self.table.setRowHeight(r, 60)
        self.table.clearSelection()
    def _row_item(self, row):
        try:
            it = self.table.item(row, 1)
            if not it:
                return None
            d = it.data(Qt.ItemDataRole.UserRole)
            return d if isinstance(d, dict) else None
        except Exception:
            return None
    def _toggle_favorite(self, item):
        key = self._cmd_key(item)
        if not key:
            return
        if key in self._favorites:
            self._favorites.remove(key)
        else:
            self._favorites.add(key)
        _save_mini_settings({"favorites": sorted(self._favorites)})
        self._render()
    def _toggle_favorites_only(self):
        self._favorites_only = bool(self.btn_fav.isChecked())
        _save_mini_settings({"favorites_only": self._favorites_only})
        self._render()
    def _on_cell_click(self, row, col):
        item = self._row_item(row)
        if not item:
            return
        if col == 0:
            self._toggle_favorite(item)
            return
        cmd = self._preview_cmd(item)
        if cmd:
            try:
                QApplication.clipboard().setText(cmd)
            except Exception:
                pass
    def _apply(self):
        self._render()
    def _update_status(self):
        name = _norm(self.ctx.name)
        self.status_text.setText("Live")
        self.status_target.setText(name if name else "None")
        self.status_dot.setProperty("active", bool(name))
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)
    def _preview_cmd(self, item):
        return self.rep.apply(item.get("command") or "")
    def reload(self):
        self._db_path, self._notes = SearchCore._load_cmds(self._db_path)
        self._db_mtime = SearchCore._safe_mtime(self._db_path)
        self._update_status()
        self._apply()
    def _tick(self):
        p = SearchCore._db_path()
        mt = SearchCore._safe_mtime(p)
        if p != self._db_path or mt != self._db_mtime:
            self.reload()
            return
        if self.ctx.changed():
            self.ctx.reload()
            self._update_status()
            self._render()
    def on_target_changed(self):
        self.ctx.reload()
        self._update_status()
        self._render()
class MiniTargets(QWidget):
    target_changed = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MiniTargetFrame")
        self.store = Target.Store()
        self._targets = []
        self._targets_path = self.store.targets_path
        self._targets_mtime = SearchCore._safe_mtime(self._targets_path)
        self._build_ui()
        QTimer.singleShot(0, self.reload)
        self.t = QTimer(self)
        self.t.setInterval(900)
        self.t.timeout.connect(self._tick)
        self.t.start()
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.search = QLineEdit(self)
        self.search.setObjectName("MiniSearchInput")
        self.search.setPlaceholderText("Search targets...")
        self.search.textChanged.connect(lambda _: self._apply())
        top.addWidget(self.search, 1)
        root.addLayout(top)
        self.table = QTableWidget(self)
        self.table.setObjectName("MiniCmdTable")
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Target", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.cellClicked.connect(self._on_cell_click)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 90)
        root.addWidget(self.table, 1)
    def _match(self, item, tokens):
        if not tokens:
            return True
        blob = item.get("name") or ""
        b = _l(blob)
        return all(t in b for t in tokens)
    def _filtered(self):
        tokens = _tokenize(self.search.text())
        return [t for t in (self._targets or []) if self._match(t, tokens)]
    def _status_text(self, st):
        if _l(st) == "live":
            return ("Live", QColor(50, 220, 140))
        return ("Not Used", QColor(180, 180, 180))
    def _render(self):
        rows = self._filtered()
        self.table.setRowCount(len(rows))
        for r, t in enumerate(rows):
            name = t.get("name") or "Unnamed"
            st_text, st_color = self._status_text(t.get("status"))
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, t)
            status_item = QTableWidgetItem(st_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(st_color)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, status_item)
            self.table.setRowHeight(r, 42)
        self.table.clearSelection()
    def _row_item(self, row):
        try:
            it = self.table.item(row, 0)
            if not it:
                return None
            d = it.data(Qt.ItemDataRole.UserRole)
            return d if isinstance(d, dict) else None
        except Exception:
            return None
    def _on_cell_click(self, row, col):
        item = self._row_item(row)
        if not item:
            return
        tid = item.get("id")
        if not tid:
            return
        self.store.set_live_target(tid)
        self.reload()
        try:
            self.target_changed.emit()
        except Exception:
            pass
    def _apply(self):
        self._render()
    def reload(self):
        self.store = Target.Store()
        self._targets = list(self.store.targets or [])
        self._targets_path = self.store.targets_path
        self._targets_mtime = SearchCore._safe_mtime(self._targets_path)
        self._apply()
    def _tick(self):
        mt = SearchCore._safe_mtime(self._targets_path)
        if mt != self._targets_mtime:
            self.reload()
class MiniWindow(QWidget):
    def __init__(self, owner=None):
        super().__init__(None)
        self._owner = owner
        self._collapsed = False
        self._expanded_size = None
        self._always_on_top = False
        self._collapsed_height = 80
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(300)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_state)
        self.setObjectName("MiniWindow")
        self.setWindowTitle("LOYA")
        ico = _abs("..", "Assets", "logox.png")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self._build_ui()
        self._load_state()
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        frame = QFrame(self)
        frame.setObjectName("MiniWindowFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(8)
        bar = QFrame(frame)
        bar.setObjectName("MiniTopBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(6)
        self.tabbar = QTabBar(bar)
        self.tabbar.setObjectName("MiniTabs")
        self.tabbar.setExpanding(False)
        self.tabbar.addTab("Commands")
        self.tabbar.addTab("LOYA")
        self.tabbar.addTab("Targets")
        bar_layout.addWidget(self.tabbar, 0)
        bar_layout.addStretch(1)
        self.btn_collapse = QToolButton(bar)
        self.btn_collapse.setObjectName("MiniControlBtn")
        self.btn_collapse.setText("v")
        self.btn_collapse.setToolTip("Collapse")
        self.btn_collapse.clicked.connect(lambda: self._set_collapsed(True))
        self.btn_expand = QToolButton(bar)
        self.btn_expand.setObjectName("MiniControlBtn")
        self.btn_expand.setText("^")
        self.btn_expand.setToolTip("Expand")
        self.btn_expand.clicked.connect(lambda: self._set_collapsed(False))
        self.btn_restore = QToolButton(bar)
        self.btn_restore.setObjectName("MiniControlBtn")
        self.btn_restore.setText("<>")
        self.btn_restore.setToolTip("Restore full app")
        self.btn_restore.clicked.connect(self._restore_full_app)
        self.btn_pin = QToolButton(bar)
        self.btn_pin.setObjectName("MiniPinBtn")
        self.btn_pin.setText("On Top")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip("Always on top")
        self.btn_pin.clicked.connect(self._toggle_on_top)
        self.btn_close = QToolButton(bar)
        self.btn_close.setObjectName("MiniControlBtn")
        self.btn_close.setText("X")
        self.btn_close.setToolTip("Close app")
        self.btn_close.clicked.connect(lambda: QApplication.instance().quit())
        for b in (self.btn_collapse, self.btn_expand, self.btn_restore, self.btn_pin, self.btn_close):
            bar_layout.addWidget(b, 0)
        frame_layout.addWidget(bar, 0)
        self.stack = QStackedWidget(frame)
        self.stack.setObjectName("MiniStack")
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.page_commands = MiniCommands(self.stack)
        if LOYA_Chat and hasattr(LOYA_Chat, "Widget"):
            self.page_loya = LOYA_Chat.Widget(self.stack)
        else:
            self.page_loya = MiniPlaceholder("LOYA", "Coming soon...", self.stack)
        self.page_targets = MiniTargets(self.stack)
        self.stack.addWidget(self.page_commands)
        self.stack.addWidget(self.page_loya)
        self.stack.addWidget(self.page_targets)
        self.stack.setCurrentIndex(0)
        self.tabbar.currentChanged.connect(self.stack.setCurrentIndex)
        self.page_targets.target_changed.connect(self.page_commands.on_target_changed)
        self.tabbar.setCurrentIndex(0)
        frame_layout.addWidget(self.stack, 1)
        root.addWidget(frame, 1)
    def _apply_geometry(self, x, y, w, h):
        g = QApplication.primaryScreen().availableGeometry()
        if x is None or y is None:
            self.resize(w, h)
            return
        nx = max(g.left(), min(int(x), g.right() - max(80, w)))
        ny = max(g.top(), min(int(y), g.bottom() - max(80, h)))
        self.setGeometry(nx, ny, w, h)
    def _load_state(self):
        cfg = _get_mini_settings()
        w = cfg.get("w")
        h = cfg.get("h")
        x = cfg.get("x")
        y = cfg.get("y")
        self._expanded_size = QSize(w, h)
        self._collapsed = bool(cfg.get("collapsed", False))
        self._always_on_top = bool(cfg.get("always_on_top", False))
        self._apply_geometry(x, y, w, h)
        self._set_on_top(self._always_on_top, apply=False)
        self.btn_pin.setChecked(self._always_on_top)
        self._set_collapsed(self._collapsed, save=False)
    def _save_state(self):
        size = self._expanded_size or self.size()
        _save_mini_settings(
            {
                "x": int(self.x()),
                "y": int(self.y()),
                "w": int(size.width()),
                "h": int(size.height()),
                "collapsed": bool(self._collapsed),
                "always_on_top": bool(self._always_on_top),
            }
        )
    def _schedule_save(self):
        if not self._save_timer.isActive():
            self._save_timer.start()
    def _set_on_top(self, on, apply=True):
        self._always_on_top = bool(on)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        if apply:
            self.show()
        self._save_state()
    def _toggle_on_top(self):
        self._set_on_top(self.btn_pin.isChecked())
    def _set_collapsed(self, collapsed, save=True):
        collapsed = bool(collapsed)
        if collapsed and not self._collapsed:
            self._expanded_size = self.size()
        self._collapsed = collapsed
        self.btn_collapse.setEnabled(not self._collapsed)
        self.btn_expand.setEnabled(self._collapsed)
        if self._collapsed:
            self.tabbar.setVisible(False)
            self.stack.setVisible(False)
            self.setMinimumHeight(self._collapsed_height)
            self.setMaximumHeight(self._collapsed_height)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.tabbar.setVisible(True)
            self.stack.setVisible(True)
            if self._expanded_size:
                self.resize(self._expanded_size)
        if save:
            self._save_state()
    def _restore_full_app(self):
        self._save_state()
        if self._owner and hasattr(self._owner, "restore_from_mini"):
            try:
                self._owner.restore_from_mini()
            except Exception:
                pass
    def moveEvent(self, e):
        super().moveEvent(e)
        if not self._collapsed:
            self._expanded_size = self.size()
        self._schedule_save()
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._collapsed:
            self._expanded_size = self.size()
        self._schedule_save()
    def closeEvent(self, e):
        try:
            self._save_state()
        finally:
            QApplication.instance().quit()
