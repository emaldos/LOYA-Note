import os
import json
import re
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QColor, QAction, QTextCharFormat, QTextCursor, QTextListFormat, QShortcut, QKeySequence
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
    QTextEdit,
    QMenu,
    QMessageBox,
)
from Cores import SearchCore, Target, CommandRelated
def _abs(*p):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)
def _data_dir():
    d = _abs("..", "Data")
    os.makedirs(d, exist_ok=True)
    return d
def _settings_path():
    return os.path.join(_data_dir(), "settings.json")
def _quick_space_path():
    return os.path.join(_data_dir(), "QuicSpace.json")
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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._ctx_menu)
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
    def _has_related_note(self,item):
        return bool(CommandRelated.related_notes(self._db_path or SearchCore._db_path(),item))
    def _notes_page(self):
        win=self.window()
        owner=getattr(win,"_owner",None)
        if owner:
            try:win._restore_full_app()
            except Exception:
                try:owner.restore_from_mini()
                except Exception:pass
            try:owner.on_nav("notes")
            except Exception:pass
            return getattr(owner,"page_notes",None)
        return None
    def _open_related_note(self,item):
        return CommandRelated.open_related_notes(self,item,self._db_path or SearchCore._db_path(),self._notes_page)
    def _ctx_menu(self,pos):
        ix=self.table.indexAt(pos)
        if not ix.isValid():return
        row=ix.row();self.table.selectRow(row);item=self._row_item(row)
        if not item:return
        menu=QMenu(self)
        open_note=QAction("Open Related Note",self);open_note.setEnabled(self._has_related_note(item));open_note.triggered.connect(lambda:self._on_open_related_note(item))
        copy_cmd=QAction("Copy Command",self);copy_cmd.triggered.connect(lambda:self._copy_command(item))
        menu.addAction(open_note);menu.addAction(copy_cmd)
        menu.exec(self.table.viewport().mapToGlobal(pos))
    def _copy_command(self,item):
        cmd=self._preview_cmd(item)
        if cmd:
            try:QApplication.clipboard().setText(cmd)
            except Exception:pass
    def _on_open_related_note(self,item):
        res=self._open_related_note(item)
        if res is None or res:return
        QMessageBox.information(self,"Open Note","Related note not found.")
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
class MiniQuickSpace(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("MiniQuickFrame")
        self._loading=False
        self._matches=[]
        self._match_index=-1
        self._save_flash_id=0
        self._save_timer=QTimer(self)
        self._save_timer.setInterval(1000)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._auto_save)
        self._build_ui()
        self._load()
    def _build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(8,8,8,8);root.setSpacing(8)
        self.search_bar=QFrame(self);self.search_bar.setObjectName("MiniQuickSearch");self.search_bar.setVisible(False)
        sr=QHBoxLayout(self.search_bar);sr.setContentsMargins(6,4,6,4);sr.setSpacing(6)
        self.search=QLineEdit(self.search_bar);self.search.setObjectName("MiniSearchInput");self.search.setPlaceholderText("Find...")
        self.btn_prev=self._tool(self.search_bar,"Up Arrow.png","^","Previous")
        self.btn_next=self._tool(self.search_bar,"Down Arrow.png","v","Next")
        self.lbl_count=QLabel("",self.search_bar);self.lbl_count.setObjectName("MiniQuickCount")
        self.btn_close=self._tool(self.search_bar,"","X","Close Search")
        sr.addWidget(self.search,1);sr.addWidget(self.btn_prev,0);sr.addWidget(self.btn_next,0);sr.addWidget(self.lbl_count,0);sr.addWidget(self.btn_close,0)
        root.addWidget(self.search_bar,0)
        self.edit=QTextEdit(self);self.edit.setObjectName("MiniQuickText");self.edit.setAcceptRichText(True);self.edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded);self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.edit.customContextMenuRequested.connect(self._context_menu)
        self.edit.textChanged.connect(self._on_changed)
        root.addWidget(self.edit,1)
        bar=QFrame(self);bar.setObjectName("MiniQuickToolbar")
        br=QHBoxLayout(bar);br.setContentsMargins(0,0,0,0);br.setSpacing(6)
        self.btn_b=self._tool(bar,"bold.png","B","Bold");self.btn_i=self._tool(bar,"italic.png","I","Italic");self.btn_u=self._tool(bar,"underline.png","U","Underline");self.btn_list=self._tool(bar,"List.png","List","Bulleted List")
        self.save_mark=QFrame(bar);self.save_mark.setObjectName("MiniQuickSaveMark");self.save_mark.setProperty("active",False);self.save_mark.setFixedSize(10,10)
        self.btn_save=self._tool(bar,"Save.png","Save","Save")
        for b in (self.btn_b,self.btn_i,self.btn_u):b.setCheckable(True)
        self.btn_b.clicked.connect(self._fmt_bold);self.btn_i.clicked.connect(self._fmt_italic);self.btn_u.clicked.connect(self._fmt_under);self.btn_list.clicked.connect(self._fmt_list);self.btn_save.clicked.connect(lambda _:self.save_now())
        for b in (self.btn_b,self.btn_i,self.btn_u,self.btn_list):br.addWidget(b,0)
        br.addStretch(1)
        br.addWidget(self.save_mark,0);br.addWidget(self.btn_save,0)
        root.addWidget(bar,0)
        self.search.textChanged.connect(self._search_changed)
        self.btn_prev.clicked.connect(lambda:self._move_match(-1))
        self.btn_next.clicked.connect(lambda:self._move_match(1))
        self.btn_close.clicked.connect(self._close_search)
        QShortcut(QKeySequence("Ctrl+F"),self,activated=self._show_search)
        QShortcut(QKeySequence("Ctrl+S"),self,activated=self.save_now)
        QShortcut(QKeySequence("Esc"),self,activated=self._close_search)
    def _tool(self,parent,icon,text,tip):
        b=QToolButton(parent);b.setObjectName("MiniQuickBtn");b.setCursor(Qt.CursorShape.PointingHandCursor);b.setToolTip(tip);b.setFixedSize(32,28)
        p=_abs("..","Assets",icon) if icon else ""
        if p and os.path.isfile(p):b.setIcon(QIcon(p));b.setIconSize(QSize(16,16));b.setText("")
        else:b.setText(text)
        return b
    def _load(self):
        self._loading=True
        data=_read_json(_quick_space_path(),{})
        if not isinstance(data,dict):data={}
        html=data.get("html","")
        text=data.get("text","")
        wrap=bool(data.get("wrap",True))
        if html:self.edit.setHtml(html)
        elif text:self.edit.setPlainText(text)
        self._set_wrap(wrap)
        self._loading=False
    def _auto_save(self):
        self._save(True)
    def _save(self,flash=False):
        data={"html":self.edit.toHtml(),"text":self.edit.toPlainText(),"wrap":self.edit.lineWrapMode()!=QTextEdit.LineWrapMode.NoWrap}
        if _write_json(_quick_space_path(),data) and flash:self._flash_save_mark()
    def save_now(self):
        if self._loading:return
        self._save_timer.stop();self._save(True)
    def _flash_save_mark(self):
        self._save_flash_id+=1;n=self._save_flash_id;self._set_save_mark(True);QTimer.singleShot(500,lambda:self._hide_save_mark(n))
    def _hide_save_mark(self,n):
        if n==self._save_flash_id:self._set_save_mark(False)
    def _set_save_mark(self,on):
        self.save_mark.setProperty("active",bool(on));self.save_mark.style().unpolish(self.save_mark);self.save_mark.style().polish(self.save_mark);self.save_mark.update()
    def _on_changed(self):
        if self._loading:return
        self._save_timer.start()
        if self.search_bar.isVisible() and _norm(self.search.text()):self._highlight()
    def _merge_fmt(self,fmt):
        cur=self.edit.textCursor()
        if not cur.hasSelection():cur.select(QTextCursor.SelectionType.WordUnderCursor)
        cur.mergeCharFormat(fmt);self.edit.mergeCurrentCharFormat(fmt);self.edit.setTextCursor(cur);self._on_changed()
    def _fmt_bold(self):
        fmt=QTextCharFormat();fmt.setFontWeight(900 if self.btn_b.isChecked() else 400);self._merge_fmt(fmt)
    def _fmt_italic(self):
        fmt=QTextCharFormat();fmt.setFontItalic(bool(self.btn_i.isChecked()));self._merge_fmt(fmt)
    def _fmt_under(self):
        fmt=QTextCharFormat();fmt.setFontUnderline(bool(self.btn_u.isChecked()));self._merge_fmt(fmt)
    def _fmt_list(self):
        cur=self.edit.textCursor();lf=QTextListFormat();lf.setStyle(QTextListFormat.Style.ListDisc);lf.setIndent(1);cur.insertList(lf);self.edit.setTextCursor(cur);self._on_changed()
    def _set_wrap(self,on):
        self.edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if on else QTextEdit.LineWrapMode.NoWrap)
    def _context_menu(self,pos):
        m=self.edit.createStandardContextMenu()
        self._strip_unicode_actions(m)
        m.addSeparator()
        wrap=QAction("Word Wrap",self);wrap.setCheckable(True);wrap.setChecked(self.edit.lineWrapMode()!=QTextEdit.LineWrapMode.NoWrap)
        wrap.triggered.connect(lambda checked:self._toggle_wrap(checked))
        m.addAction(wrap)
        m.exec(self.edit.viewport().mapToGlobal(pos))
    def _strip_unicode_actions(self,m):
        for a in list(m.actions()):
            t=(a.text() or "").replace("&","").lower()
            sm=a.menu()
            if "unicode" in t and "control" in t:
                m.removeAction(a);continue
            if sm:self._strip_unicode_actions(sm)
    def _toggle_wrap(self,checked):
        self._set_wrap(bool(checked));self._save_timer.start()
    def _show_search(self):
        self.search_bar.setVisible(True);self.search.setFocus();self.search.selectAll();self._highlight()
    def _close_search(self):
        self.search_bar.setVisible(False);self.search.clear();self._clear_highlight();self.edit.setFocus()
    def _search_changed(self,text):
        if not _norm(text):
            self._clear_highlight()
            if self.search_bar.isVisible():QTimer.singleShot(0,self._close_search)
            return
        self._highlight()
    def _clear_highlight(self):
        self._matches=[];self._match_index=-1;self.edit.setExtraSelections([]);self.lbl_count.setText("")
    def _highlight(self):
        q=self.search.text()
        if not q:self._clear_highlight();return
        doc_text=self.edit.toPlainText();low=doc_text.lower();needle=q.lower();start=0;matches=[]
        while needle:
            i=low.find(needle,start)
            if i<0:break
            matches.append((i,i+len(q)));start=i+max(1,len(q))
        sels=[]
        fmt=QTextCharFormat();fmt.setBackground(QColor("#ffe86a"));fmt.setForeground(QColor("#000000"))
        doc=self.edit.document()
        for s,e in matches:
            cur=QTextCursor(doc);cur.setPosition(s);cur.setPosition(e,QTextCursor.MoveMode.KeepAnchor)
            sel=QTextEdit.ExtraSelection();sel.cursor=cur;sel.format=fmt;sels.append(sel)
        self._matches=matches
        if matches and (self._match_index<0 or self._match_index>=len(matches)):self._match_index=0
        if not matches:self._match_index=-1
        self.edit.setExtraSelections(sels);self._update_count()
    def _update_count(self):
        self.lbl_count.setText(f"{self._match_index+1}/{len(self._matches)}" if self._matches else "0/0")
    def _move_match(self,delta):
        if not self._matches:self._highlight()
        if not self._matches:return
        self._match_index=(self._match_index+delta)%len(self._matches)
        s,e=self._matches[self._match_index]
        cur=QTextCursor(self.edit.document());cur.setPosition(s);cur.setPosition(e,QTextCursor.MoveMode.KeepAnchor);self.edit.setTextCursor(cur);self.edit.ensureCursorVisible();self._update_count()
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
    def _asset_icon(self,name):
        p = _abs("..", "Assets", name)
        return QIcon(p) if os.path.isfile(p) else QIcon()
    def _apply_button_icon(self,btn,name,fallback="",size=18):
        ico = self._asset_icon(name)
        if not ico.isNull():
            btn.setIcon(ico)
            btn.setIconSize(QSize(size, size))
            btn.setText("")
        else:
            btn.setText(fallback)
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
        self.tabbar.addTab("Targets")
        self.tabbar.addTab("Quick Space")
        bar_layout.addWidget(self.tabbar, 0)
        bar_layout.addStretch(1)
        self.btn_collapse = QToolButton(bar)
        self.btn_collapse.setObjectName("MiniControlBtn")
        self.btn_collapse.setToolTip("Close preview")
        self.btn_collapse.clicked.connect(self._toggle_collapsed)
        self.btn_restore = QToolButton(bar)
        self.btn_restore.setObjectName("MiniControlBtn")
        self._apply_button_icon(self.btn_restore, "Expand.png", "<>", 18)
        self.btn_restore.setToolTip("Expand to original view")
        self.btn_restore.clicked.connect(self._restore_full_app)
        self.btn_pin = QToolButton(bar)
        self.btn_pin.setObjectName("MiniPinBtn")
        self._apply_button_icon(self.btn_pin, "pin.png", "Pin", 18)
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip("Pin on top")
        self.btn_pin.clicked.connect(self._toggle_on_top)
        for b in (self.btn_collapse, self.btn_restore, self.btn_pin):
            bar_layout.addWidget(b, 0)
        frame_layout.addWidget(bar, 0)
        self.stack = QStackedWidget(frame)
        self.stack.setObjectName("MiniStack")
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.page_commands = MiniCommands(self.stack)
        self.page_targets = MiniTargets(self.stack)
        self.page_quick = MiniQuickSpace(self.stack)
        self.stack.addWidget(self.page_commands)
        self.stack.addWidget(self.page_targets)
        self.stack.addWidget(self.page_quick)
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
    def _toggle_collapsed(self):
        self._set_collapsed(not self._collapsed)
    def _update_collapse_button(self):
        if self._collapsed:
            self._apply_button_icon(self.btn_collapse, "Down Arrow.png", "v", 18)
            self.btn_collapse.setToolTip("Open preview")
        else:
            self._apply_button_icon(self.btn_collapse, "Up Arrow.png", "^", 18)
            self.btn_collapse.setToolTip("Close preview")
    def _set_collapsed(self, collapsed, save=True):
        collapsed = bool(collapsed)
        if collapsed and not self._collapsed:
            self._expanded_size = self.size()
        self._collapsed = collapsed
        self._update_collapse_button()
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
        self._save_quick_space()
        self._save_state()
        if self._owner and hasattr(self._owner, "restore_from_mini"):
            try:
                self._owner.restore_from_mini()
            except Exception:
                pass
    def _save_quick_space(self):
        try:self.page_quick.save_now()
        except Exception:pass
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
            self._save_quick_space()
            self._save_state()
        finally:
            QApplication.instance().quit()
