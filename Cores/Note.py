import os,sqlite3,logging,hashlib,re,json,base64
from logging.handlers import RotatingFileHandler
from datetime import datetime,timezone
from PyQt6.QtCore import Qt,QSize,QTimer,pyqtSignal,QRect,QEvent
from PyQt6.QtGui import QIcon,QKeySequence,QTextCharFormat,QTextListFormat,QTextTableFormat,QTextCursor,QShortcut,QAction,QColor,QTextBlockFormat,QImage,QTextImageFormat,QTextFormat,QTextLength,QTextDocumentFragment
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QToolButton,QTextEdit,QMessageBox,QDialog,QGridLayout,QSpinBox,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMenu,QComboBox,QFileDialog,QInputDialog
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("Note");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"Note_log.log"))
    for h in list(lg.handlers):
        try:
            if getattr(h,"baseFilename","") and os.path.abspath(h.baseFilename)==fp:return lg
        except:pass
    h=RotatingFileHandler(fp,maxBytes=1024*1024,backupCount=5,encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s","%Y-%m-%d %H:%M:%S"))
    lg.addHandler(h);return lg
_LOG=None
def _log(tag,msg):
    global _LOG
    if _LOG is None:_LOG=_log_setup()
    try:_LOG.info(f"{tag} {msg}")
    except:pass
_DEFAULT_FONT_SIZE=13.0
_CODE_COLOR="#6bdcff"
_CODE_FONT="Consolas"
_CMD_ANCHOR_EDIT="cmdedit:"
_CMD_ANCHOR_DEL="cmddelete:"
try:
    _USER_PROP=int(QTextFormat.Property.UserProperty)
except Exception:
    try:_USER_PROP=int(QTextFormat.UserProperty)
    except Exception:_USER_PROP=1000
_CMD_TABLE_PROP=_USER_PROP+41
def _db_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"Note_LOYA_V1.db")
DB_SCHEMA_VERSION=2
def _ensure_schema(con):
    cur=con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS Notes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT,content TEXT,created_at TEXT,updated_at TEXT)")
    try:cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_notes_name ON Notes(note_name)")
    except:
        try:
            cur.execute("SELECT note_name,MAX(id) FROM Notes GROUP BY note_name HAVING COUNT(*)>1")
            for nm,keep in cur.fetchall():cur.execute("DELETE FROM Notes WHERE note_name=? AND id<>?",(nm,keep))
            con.commit()
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_notes_name ON Notes(note_name)")
        except:pass
    _apply_migrations(con)
    con.commit()
def _ensure_cmd_schema(con):
    cur=con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS Commands(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,created_at TEXT,updated_at TEXT)")
    try:
        cols=set(_table_cols(cur,"Commands"))
        if "note_id" not in cols:cur.execute("ALTER TABLE Commands ADD COLUMN note_id INTEGER")
        if "cmd_note_title" not in cols:cur.execute("ALTER TABLE Commands ADD COLUMN cmd_note_title TEXT")
        if "description" not in cols:cur.execute("ALTER TABLE Commands ADD COLUMN description TEXT")
    except:pass
    try:cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_note_id ON Commands(note_id)")
    except:pass
    try:cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_note_name ON Commands(note_name)")
    except:pass
    _apply_migrations(con)
    con.commit()
def _apply_migrations(con):
    try:cur=con.cursor()
    except:return
    try:
        cur.execute("PRAGMA user_version")
        row=cur.fetchone()
        ver=int(row[0]) if row and str(row[0]).isdigit() else 0
    except:ver=0
    now=datetime.now(timezone.utc).isoformat()
    try:cur.execute("CREATE TABLE IF NOT EXISTS SchemaMigrations(version INTEGER PRIMARY KEY,applied_at TEXT)")
    except:pass
    if ver<1:
        try:cur.execute("INSERT OR IGNORE INTO SchemaMigrations(version,applied_at) VALUES(1,?)",(now,))
        except:pass
        ver=1
    if ver<2:
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS NotesHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,content TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_hist_note_id ON NotesHistory(note_id)")
        except:pass
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS CommandsNotesHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,cmd_id INTEGER,note_name TEXT,category TEXT,sub_category TEXT,command TEXT,tags TEXT,description TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_hist_cmd_id ON CommandsNotesHistory(cmd_id)")
        except:pass
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS CommandsHistory(id INTEGER PRIMARY KEY AUTOINCREMENT,cmd_id INTEGER,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,action TEXT,action_at TEXT)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_hist_cmd_id ON CommandsHistory(cmd_id)")
        except:pass
        try:cur.execute("INSERT OR IGNORE INTO SchemaMigrations(version,applied_at) VALUES(2,?)",(now,))
        except:pass
        ver=2
    try:cur.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
    except:pass
    try:con.commit()
    except:pass
def _parse_cmd_blocks(text):
    t=text or ""
    out=[]
    for m in re.finditer(r"<C\s*\[(.*?)\]\s*>\s*(.*?)\s*</C>",t,re.S|re.I):
        meta=(m.group(1) or "").strip()
        body=(m.group(2) or "").rstrip()
        d={"cmd_note_title":"","category":"","sub_category":"","description":"","tags":"","command":body}
        for p in [x.strip() for x in meta.split(",") if x.strip()]:
            if ":" not in p:continue
            k,v=p.split(":",1)
            k=(k or "").strip().lower()
            v=(v or "").strip()
            if "command note tittle" in k or "note title" in k:d["cmd_note_title"]=v
            elif k=="category":d["category"]=v
            elif "sub category" in k or "subcategory" in k:d["sub_category"]=v
            elif k=="description":d["description"]=v
            elif k=="tags":d["tags"]=v
        if _norm(d["command"]):out.append(d)
    return out
def _sync_commands(con,note_id,note_name,note_text,now):
    _ensure_cmd_schema(con)
    cmds=note_text if isinstance(note_text,list) else _parse_cmd_blocks(note_text)
    cur=con.cursor()
    try:
        cur.execute("SELECT id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command FROM Commands WHERE note_id=?",(int(note_id),))
        for r in cur.fetchall():
            _insert_cmd_history(cur,r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],"delete",now)
    except:pass
    con.execute("DELETE FROM Commands WHERE note_id=?",(int(note_id),))
    for c in cmds:
        cur.execute("INSERT INTO Commands(note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(int(note_id),(note_name or "").strip(),_norm(c.get("cmd_note_title","")),_norm(c.get("category","")),_norm(c.get("sub_category","")),_norm(c.get("description","")),_norm(c.get("tags","")),(c.get("command","") or "").rstrip(),now,now))
        try:cid=int(cur.lastrowid)
        except:cid=None
        _insert_cmd_history(cur,cid,int(note_id),(note_name or "").strip(),_norm(c.get("cmd_note_title","")),_norm(c.get("category","")),_norm(c.get("sub_category","")),_norm(c.get("description","")),_norm(c.get("tags","")),(c.get("command","") or "").rstrip(),"insert",now)
    con.commit()
    return len(cmds)
def _norm(s):return " ".join((s or "").strip().split())
def _cmd_id(data):
    parts=[
        _norm(data.get("cmd_note_title","")),
        _norm(data.get("category","")),
        _norm(data.get("sub_category","")),
        _norm(data.get("description","")),
        _norm(data.get("tags","")),
        _norm(data.get("command","")),
    ]
    raw="|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12] if raw else ""
def _encode_cmd_data(data):
    if not isinstance(data,dict):return ""
    d=dict(data)
    if not _norm(d.get("cid","")):d["cid"]=_cmd_id(d)
    raw=json.dumps(d,ensure_ascii=False)
    b=base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
    return b.rstrip("=")
def _decode_cmd_data(token):
    t=_norm(token)
    if not t:return {}
    pad="="*((4-len(t)%4)%4)
    try:
        raw=base64.urlsafe_b64decode(t+pad).decode("utf-8")
        d=json.loads(raw)
        return d if isinstance(d,dict) else {}
    except Exception:
        return {}
def _parse_cmd_meta(meta):
    d={"cmd_note_title":"","category":"","sub_category":"","description":"","tags":""}
    for p in [x.strip() for x in (meta or "").split(",") if x.strip()]:
        if ":" not in p:continue
        k,v=p.split(":",1)
        k=(k or "").strip().lower()
        v=(v or "").strip()
        if "command note tittle" in k or "note title" in k:d["cmd_note_title"]=v
        elif k=="category":d["category"]=v
        elif "sub category" in k or "subcategory" in k:d["sub_category"]=v
        elif k=="description":d["description"]=v
        elif k=="tags":d["tags"]=v
    return d
def _table_cols(cur,t):
    try:cur.execute(f"PRAGMA table_info({t})");return [r[1] for r in cur.fetchall()]
    except:return []
def _cmd_meta(dbp):
    cats=set();subm={}
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            cur=con.cursor()
            for t in ("CommandsNotes","Commands"):
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(t,))
                if not cur.fetchone():continue
                cols=[c.lower() for c in _table_cols(cur,t)]
                if "category" not in cols:continue
                subcol="sub_category" if "sub_category" in cols else ("subcategory" if "subcategory" in cols else "")
                if not subcol:continue
                cur.execute(f"SELECT DISTINCT category,{subcol} FROM {t} WHERE category IS NOT NULL AND TRIM(category)!=''")
                for c,sc in cur.fetchall():
                    c=_norm(c);sc=_norm(sc)
                    if not c:continue
                    cats.add(c);subm.setdefault(c,set())
                    if sc:subm[c].add(sc)
    except:pass
    cats=sorted(list(cats),key=lambda x:x.lower())
    return cats,{c:sorted(list(subm.get(c,set())),key=lambda x:x.lower()) for c in cats}
class DropInput(QWidget):
    def __init__(self,obj,ph="",parent=None):
        super().__init__(parent)
        self.e=QLineEdit(self);self.e.setObjectName(obj);self.e.setPlaceholderText(ph)
        self.b=QToolButton(self);self.b.setObjectName(obj+"Drop");self.b.setCursor(Qt.CursorShape.PointingHandCursor);self.b.setText("▼")
        self.b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b.setStyleSheet("QToolButton{padding:0;text-align:center} QToolButton::menu-indicator{image:none;width:0;height:0}")
        self.m=QMenu(self.b)
        self.m.setStyleSheet("QMenu{background:#1e1e1e;border:1px solid #2b2b2b;border-radius:12px} QMenu::item{padding:8px 14px} QMenu::item:selected{background:#2b2b2b}")
        self.b.setMenu(self.m)
        h=38
        self.e.setMinimumHeight(h);self.e.setMaximumHeight(h)
        self.b.setFixedSize(34,h)
        lay=QHBoxLayout(self);lay.setContentsMargins(0,0,0,0);lay.setSpacing(8)
        lay.addWidget(self.e,1);lay.addWidget(self.b,0)
        self.setFocusProxy(self.e)
    def text(self):return self.e.text()
    def setText(self,t):self.e.setText(t or "")
    def clear(self):self.e.clear()
    def setReadOnly(self,x):self.e.setReadOnly(bool(x))
    def lineEdit(self):return self.e
    def set_items(self,items,empty_label):
        self.m.clear()
        items=list(items or [])
        if not items:
            a=QAction(empty_label,self);a.setEnabled(False);self.m.addAction(a);return
        for s in items:
            a=QAction(s,self);a.triggered.connect(lambda chk=False,v=s:self.setText(v));self.m.addAction(a)
def _sig(name,htmls):
    s=(name or "").strip()+"\n"+(htmls or "")
    return hashlib.sha256(s.encode("utf-8","ignore")).hexdigest()
def _insert_note_history(cur,note_id,note_name,content,action,action_at):
    try:
        cur.execute("INSERT INTO NotesHistory(note_id,note_name,content,action,action_at) VALUES(?,?,?,?,?)",(note_id,note_name,content,action,action_at))
    except:pass
def _insert_cmd_history(cur,cmd_id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,action,action_at):
    try:
        cur.execute("INSERT INTO CommandsHistory(cmd_id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,action,action_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(cmd_id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,action,action_at))
    except:pass
def _load_notes(dbp):
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con)
            cur=con.cursor()
            cur.execute("SELECT id,note_name,content,created_at,updated_at FROM Notes ORDER BY updated_at DESC")
            rows=cur.fetchall()
        out=[]
        for r in rows:out.append({"id":r[0],"note_name":(r[1] or "").strip(),"content":r[2] or "","created_at":r[3] or "","updated_at":r[4] or ""})
        return out
    except Exception as e:
        _log("[!]",f"Load notes failed ({e})")
        return []
def _delete_note(dbp,name):
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con);_ensure_cmd_schema(con)
            cur=con.cursor()
            cur.execute("SELECT id,note_name,content FROM Notes WHERE note_name=?",(name,))
            r=cur.fetchone()
            if not r:return False
            nid=int(r[0]);now=datetime.now(timezone.utc).isoformat()
            _insert_note_history(cur,nid,r[1] or "",r[2] or "","delete",now)
            try:
                cur.execute("SELECT id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command FROM Commands WHERE note_id=?",(nid,))
                for row in cur.fetchall():
                    _insert_cmd_history(cur,row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],"delete",now)
            except:pass
            con.execute("DELETE FROM Commands WHERE note_id=?",(nid,))
            cur.execute("DELETE FROM Notes WHERE id=?",(nid,))
            con.commit()
            return bool(cur.rowcount)
    except Exception as e:
        _log("[!]",f"Delete note failed ({e})")
        return False
class _TableDlg(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("TableDlg")
        self.setWindowTitle("Insert Table (C,R)")
        self.setFixedSize(320,150)
        v=QVBoxLayout(self);v.setContentsMargins(14,14,14,14);v.setSpacing(10)
        g=QGridLayout();g.setContentsMargins(0,0,0,0);g.setHorizontalSpacing(10);g.setVerticalSpacing(10)
        g.addWidget(QLabel("C",self),0,0);g.addWidget(QLabel("R",self),0,1)
        self.c=QSpinBox(self);self.c.setRange(1,50);self.c.setValue(2)
        self.r=QSpinBox(self);self.r.setRange(1,50);self.r.setValue(3)
        g.addWidget(self.c,1,0);g.addWidget(self.r,1,1)
        v.addLayout(g)
        b=QHBoxLayout();b.setContentsMargins(0,0,0,0);b.setSpacing(10)
        self.ok=QToolButton(self);self.ok.setObjectName("TableOk");self.ok.setCursor(Qt.CursorShape.PointingHandCursor);self.ok.setText("Insert")
        self.ca=QToolButton(self);self.ca.setObjectName("TableCancel");self.ca.setCursor(Qt.CursorShape.PointingHandCursor);self.ca.setText("Cancel")
        self.ok.clicked.connect(self.accept);self.ca.clicked.connect(self.reject)
        b.addStretch(1);b.addWidget(self.ok,0,Qt.AlignmentFlag.AlignCenter);b.addWidget(self.ca,0,Qt.AlignmentFlag.AlignCenter);b.addStretch(1)
        v.addLayout(b)
    def vals(self):return int(self.c.value()),int(self.r.value())
class _CmdBlockDlg(QDialog):
    def __init__(self,parent,title_value=""):
        super().__init__(parent)
        self.setObjectName("CommandsAddDialog")
        self.setWindowTitle("Add Command Block")
        self.resize(980,640)
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        root=QVBoxLayout(self);root.setContentsMargins(14,14,14,14);root.setSpacing(12)
        box=QFrame(self);box.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(box);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        head=QHBoxLayout();head.setSpacing(10)
        t=QLabel("Command Block",box);t.setObjectName("TargetFormTitle")
        head.addWidget(t,1)
        v.addLayout(head)
        g=QGridLayout();g.setContentsMargins(0,0,0,0);g.setHorizontalSpacing(12);g.setVerticalSpacing(10)
        self.in_title=QLineEdit(box);self.in_title.setObjectName("CmdNoteName");self.in_title.setPlaceholderText("Required");self.in_title.setText((title_value or "").strip());self.in_title.setReadOnly(True)
        self.in_cat=DropInput("CmdCategory","Required",box)
        self.in_sub=DropInput("CmdSubCategory","Required",box)
        self.in_tags=QLineEdit(box);self.in_tags.setObjectName("TagInput");self.in_tags.setPlaceholderText("word,word,word")
        self.in_desc=QLineEdit(box);self.in_desc.setObjectName("CmdDescription");self.in_desc.setPlaceholderText("Optional")
        self.in_prog=QLineEdit(box);self.in_prog.setObjectName("CmdDescription");self.in_prog.setPlaceholderText("Program/Tool (optional)")
        g.addWidget(QLabel("Note Title",box),0,0);g.addWidget(self.in_title,0,1)
        g.addWidget(QLabel("Category",box),0,2);g.addWidget(self.in_cat,0,3)
        g.addWidget(QLabel("Sub Category",box),0,4);g.addWidget(self.in_sub,0,5)
        g.addWidget(QLabel("Tags",box),1,0);g.addWidget(self.in_tags,1,1,1,3)
        g.addWidget(QLabel("Description",box),1,4);g.addWidget(self.in_desc,1,5)
        g.addWidget(QLabel("Program",box),2,0);g.addWidget(self.in_prog,2,1,1,5)
        v.addLayout(g)
        v.addWidget(QLabel("Command",box),0)
        self.in_cmd=QTextEdit(box);self.in_cmd.setObjectName("CmdCommand");self.in_cmd.setPlaceholderText("Enter command here...")
        self.in_cmd.setAcceptRichText(False)
        v.addWidget(self.in_cmd,1)
        fb=QHBoxLayout();fb.setContentsMargins(0,0,0,0);fb.setSpacing(10)
        self.btn_ok=QToolButton(box);self.btn_ok.setObjectName("CmdSaveBtn");self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ok.setText("Insert")
        self.btn_ca=QToolButton(box);self.btn_ca.setObjectName("CmdCancelBtn");self.btn_ca.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ca.setText("Cancel")
        self.btn_ok.clicked.connect(self._ok)
        self.btn_ca.clicked.connect(self.reject)
        fb.addStretch(1);fb.addWidget(self.btn_ok,0);fb.addWidget(self.btn_ca,0)
        v.addLayout(fb)
        root.addWidget(box,1)
        for w in (self.in_title,self.in_cat,self.in_sub,self.in_tags,self.in_desc,self.in_prog):w.setMinimumHeight(34)
        self.btn_ok.setMinimumHeight(34);self.btn_ca.setMinimumHeight(34)
        self._vals=None
        cats,subs=_cmd_meta(_db_path())
        self.in_cat.set_items(cats,"Type a Category")
        self.in_sub.set_items([],"Type a Sub Category")
        def _subs_for(cat):
            c=_norm(cat)
            if not c:return []
            if c in subs:return subs[c]
            lc=c.lower()
            for k,v in subs.items():
                kl=k.lower()
                if kl==lc or kl.startswith(lc):return v
            return []
        def _sync_sub():
            self.in_sub.set_items(_subs_for(self.in_cat.text()),"Type a Sub Category")
        le=self.in_cat.lineEdit()
        try:le.textChanged.disconnect()
        except:pass
        le.textChanged.connect(lambda _=None:_sync_sub())
        _sync_sub()
        try:le.setFocus()
        except:self.in_cat.setFocus()
    def _ok(self):
        title=_norm(self.in_title.text())
        cat=_norm(self.in_cat.text())
        sub=_norm(self.in_sub.text())
        tags=_norm(self.in_tags.text())
        desc=_norm(self.in_desc.text())
        prog=_norm(self.in_prog.text())
        cmd=(self.in_cmd.toPlainText() or "").rstrip()
        if not title or not cat or not sub:
            QMessageBox.warning(self,"Missing","Note Title, Category, and Sub Category are required.")
            return
        if not cmd:
            QMessageBox.warning(self,"Missing","Command is required.")
            return
        self._vals={"title":title,"category":cat,"sub":sub,"tags":tags,"description":desc,"program":prog,"command":cmd}
        self.accept()
    def vals(self):return self._vals
class NoteEdit(QTextEdit):
    def __init__(self,on_add_cmd,on_enter,on_cmd_anchor=None,is_cmd_table=None,parent=None):
        super().__init__(parent)
        self._on_add_cmd=on_add_cmd
        self._on_enter=on_enter
        self._on_cmd_anchor=on_cmd_anchor
        self._is_cmd_table=is_cmd_table if callable(is_cmd_table) else (lambda _t: False)
        self._img_resize_active=False
        self._img_resize_pos=None
        self._img_resize_start=None
        self._img_resize_base=None
        self._img_resize_ratio=1.0
        self.setObjectName("NoteArea")
        self.setAcceptRichText(True)
        self._tbl_tool=QToolButton(self.viewport())
        self._tbl_tool.setObjectName("NoteTableTool")
        self._tbl_tool.setText("#")
        self._tbl_tool.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tbl_tool.setAutoRaise(True)
        self._tbl_tool.hide()
        self._tbl_del=QToolButton(self.viewport())
        self._tbl_del.setObjectName("NoteTableDel")
        self._tbl_del.setText("X")
        self._tbl_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tbl_del.setAutoRaise(True)
        self._tbl_del.hide()
        self._tbl_menu=QMenu(self._tbl_tool)
        self._tbl_menu.aboutToShow.connect(self._build_table_menu)
        self._tbl_tool.setMenu(self._tbl_menu)
        self._tbl_tool.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._tbl_tool.clicked.connect(self._show_table_menu)
        self._tbl_del.clicked.connect(self._delete_active_table)
        self._tbl_tool.installEventFilter(self)
        self._active_table=None
        self._active_cell=(0,0)
        self._fixing_cmd_cell=False
        self.cursorPositionChanged.connect(self._update_table_tools)
        self.cursorPositionChanged.connect(self._fix_cmd_control_cell)
        try:self.verticalScrollBar().valueChanged.connect(self._update_table_tools)
        except Exception:pass
    def keyPressEvent(self,e):
        key=e.key()
        mods=e.modifiers()
        is_enter=key in (Qt.Key.Key_Return,Qt.Key.Key_Enter)
        plain_enter=is_enter and not (mods&(Qt.KeyboardModifier.ShiftModifier|Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier))
        cursor=self.textCursor()
        table=cursor.currentTable()
        if table and self._is_cmd_table(table):
            if mods&Qt.KeyboardModifier.ControlModifier:
                if key in (Qt.Key.Key_C,Qt.Key.Key_A,Qt.Key.Key_Insert):
                    super().keyPressEvent(e);return
            if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Tab,Qt.Key.Key_Backspace,Qt.Key.Key_Delete) or (e.text() and not (mods&Qt.KeyboardModifier.ControlModifier)):
                e.accept();return
        if table and not self._is_cmd_table(table):
            if key==Qt.Key.Key_Tab:
                self._table_next_cell(table,cursor);e.accept();return
            if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
                self._table_new_row(table,cursor);e.accept();return
        super().keyPressEvent(e)
        if plain_enter and not table:
            try:self._on_enter()
            except:pass
    def contextMenuEvent(self,e):
        cur=self.cursorForPosition(e.pos())
        self.setTextCursor(cur)
        m=self.createStandardContextMenu()
        for a in list(m.actions()):
            t=(a.text() or "").lower()
            if "unicode" in t:m.removeAction(a)
        m.addSeparator()
        a=m.addAction("Add Command Here")
        a.triggered.connect(lambda:self._on_add_cmd(True))
        m.exec(e.globalPos())
    def eventFilter(self,obj,event):
        if obj is self._tbl_tool and event.type()==QEvent.Type.ContextMenu:
            self._show_table_menu()
            return True
        return super().eventFilter(obj,event)
    def _fix_cmd_control_cell(self):
        if self._fixing_cmd_cell:return
        try:
            cur=self.textCursor()
            table=cur.currentTable()
            if not table or not self._is_cmd_table(table):return
            cell=table.cellAt(cur)
            if not cell.isValid() or cell.column()!=1:return
            self._fixing_cmd_cell=True
            nc=table.cellAt(cell.row(),0).lastCursorPosition()
            self.setTextCursor(nc)
        except Exception:
            pass
        finally:
            self._fixing_cmd_cell=False
    def _table_at_cursor(self):
        cur=self.textCursor()
        table=cur.currentTable()
        if not table or self._is_cmd_table(table):return None,None,None
        cell=table.cellAt(cur)
        return table,cell.row(),cell.column()
    def _table_next_cell(self,table,cur):
        cell=table.cellAt(cur)
        row=cell.row();col=cell.column()
        if col<table.columns()-1:
            col+=1
        elif row<table.rows()-1:
            row+=1;col=0
        else:
            table.insertRows(table.rows(),1)
            row=table.rows()-1;col=0
        nc=table.cellAt(row,col).firstCursorPosition()
        self.setTextCursor(nc)
    def _table_new_row(self,table,cur):
        cell=table.cellAt(cur)
        row=cell.row()
        table.insertRows(row+1,1)
        nc=table.cellAt(row+1,0).firstCursorPosition()
        self.setTextCursor(nc)
    def _update_table_tools(self):
        table,row,col=self._table_at_cursor()
        if not table:
            self._active_table=None
            self._tbl_tool.hide();self._tbl_del.hide()
            return
        self._active_table=table
        self._active_cell=(row,col)
        self._position_table_tools(table)
        self._tbl_tool.show();self._tbl_del.show()
    def _position_table_tools(self,table):
        try:
            cell0=table.cellAt(0,0)
            cell1=table.cellAt(table.rows()-1,table.columns()-1)
            r0=self.cursorRect(cell0.firstCursorPosition())
            r1=self.cursorRect(cell1.lastCursorPosition())
            x=r1.right()+6
            y=r0.top()
            viewport=self.viewport()
            if x+self._tbl_tool.width()>viewport.width():x=max(0,viewport.width()-self._tbl_tool.width()-4)
            if y<0:y=0
            self._tbl_tool.move(x,y)
            self._tbl_del.move(x,y+self._tbl_tool.height()+4)
        except Exception:
            pass
    def _show_table_menu(self):
        try:self._tbl_menu.popup(self._tbl_tool.mapToGlobal(self._tbl_tool.rect().bottomLeft()))
        except Exception:pass
    def _build_table_menu(self):
        self._tbl_menu.clear()
        table=self._active_table
        if not table:return
        row,col=self._active_cell
        self._tbl_menu.addAction("Add row above",lambda:table.insertRows(max(0,row),1))
        self._tbl_menu.addAction("Add row below",lambda:table.insertRows(row+1,1))
        self._tbl_menu.addSeparator()
        self._tbl_menu.addAction("Add column left",lambda:table.insertColumns(max(0,col),1))
        self._tbl_menu.addAction("Add column right",lambda:table.insertColumns(col+1,1))
        self._tbl_menu.addSeparator()
        self._tbl_menu.addAction("Move row up",lambda:self._swap_rows(table,row,row-1))
        self._tbl_menu.addAction("Move row down",lambda:self._swap_rows(table,row,row+1))
        self._tbl_menu.addSeparator()
        self._tbl_menu.addAction("Delete row",lambda:table.removeRows(row,1) if table.rows()>1 else self._delete_table(table))
        self._tbl_menu.addAction("Delete column",lambda:table.removeColumns(col,1) if table.columns()>1 else self._delete_table(table))
        self._tbl_menu.addSeparator()
        self._tbl_menu.addAction("Merge selected cells",lambda:self._merge_selected_cells(table))
        self._tbl_menu.addAction("Split cell",lambda:self._split_cell(table,row,col))
    def _delete_active_table(self):
        self._delete_table(self._active_table)
    def _delete_table(self,table):
        if not table:return
        try:
            cur=table.firstCursorPosition()
            cur.select(QTextCursor.SelectionType.TableUnderCursor)
            cur.removeSelectedText()
            cur.deleteChar()
        except Exception:
            pass
    def _cell_fragment(self,cell):
        c=cell.firstCursorPosition()
        c.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
        return QTextDocumentFragment(c)
    def _set_cell_fragment(self,cell,frag):
        c=cell.firstCursorPosition()
        c.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        c.insertFragment(frag)
    def _swap_rows(self,table,r1,r2):
        if r2<0 or r2>=table.rows():return
        cols=table.columns()
        fr1=[self._cell_fragment(table.cellAt(r1,c)) for c in range(cols)]
        fr2=[self._cell_fragment(table.cellAt(r2,c)) for c in range(cols)]
        for c in range(cols):
            self._set_cell_fragment(table.cellAt(r1,c),fr2[c])
            self._set_cell_fragment(table.cellAt(r2,c),fr1[c])
    def _merge_selected_cells(self,table):
        cur=self.textCursor()
        if not cur.hasSelection():
            return
        s=cur.selectionStart();e=cur.selectionEnd()
        c1=QTextCursor(self.document());c1.setPosition(s)
        c2=QTextCursor(self.document());c2.setPosition(e)
        cell1=table.cellAt(c1);cell2=table.cellAt(c2)
        if not cell1.isValid() or not cell2.isValid():return
        r1=min(cell1.row(),cell2.row());c1=min(cell1.column(),cell2.column())
        r2=max(cell1.row()+cell1.rowSpan()-1,cell2.row()+cell2.rowSpan()-1)
        c2=max(cell1.column()+cell1.columnSpan()-1,cell2.column()+cell2.columnSpan()-1)
        table.mergeCells(r1,c1,(r2-r1+1),(c2-c1+1))
    def _split_cell(self,table,row,col):
        cell=table.cellAt(row,col)
        if not cell.isValid():return
        rs=cell.rowSpan();cs=cell.columnSpan()
        if rs>1 or cs>1:
            table.splitCell(row,col,rs,cs)
    def _image_rect_at(self,pos):
        cur=self.cursorForPosition(pos)
        fmt=cur.charFormat()
        if not fmt.isImageFormat():return None,None,None
        img=fmt.toImageFormat()
        rect=self.cursorRect(cur)
        w=img.width();h=img.height()
        if w<=0 or h<=0:
            qimg=QImage(img.name())
            if not qimg.isNull():
                w=qimg.width();h=qimg.height()
        if w>0 and h>0:
            rect.setWidth(int(w));rect.setHeight(int(h))
        return cur,img,rect
    def _image_handle_at(self,pos):
        cur,img,rect=self._image_rect_at(pos)
        if not cur or rect.isNull():return None,None,None
        handle=12
        m=min(rect.width(),rect.height())
        if m>0 and m<handle:handle=max(6,int(m/2))
        hx=rect.right()-handle+1
        hy=rect.bottom()-handle+1
        hrect=QRect(hx,hy,handle,handle)
        if hrect.contains(pos):return cur,img,rect
        return None,None,None
    def _apply_image_size(self,pos,w,h):
        doc=self.document()
        if pos is None or pos<0 or pos>=doc.characterCount():return
        c=QTextCursor(doc)
        c.setPosition(int(pos))
        c.setPosition(min(int(pos)+1,doc.characterCount()-1),QTextCursor.MoveMode.KeepAnchor)
        fmt=c.charFormat()
        if not fmt.isImageFormat():return
        img=fmt.toImageFormat()
        img.setWidth(float(w));img.setHeight(float(h))
        c.setCharFormat(img)
    def mousePressEvent(self,e):
        self._img_resize_active=False
        href=self.anchorAt(e.pos())
        if href and (href.startswith(_CMD_ANCHOR_EDIT) or href.startswith(_CMD_ANCHOR_DEL)):
            try:
                cur=self.cursorForPosition(e.pos())
                self.setTextCursor(cur)
                if callable(self._on_cmd_anchor):self._on_cmd_anchor(href,cur)
            except Exception:
                pass
            e.accept()
            return
        try:
            cur=self.cursorForPosition(e.pos())
            table=cur.currentTable()
            if table and self._is_cmd_table(table):
                cell=table.cellAt(cur)
                if cell.isValid() and cell.column()==1:
                    self._fixing_cmd_cell=True
                    try:
                        nc=table.cellAt(cell.row(),0).lastCursorPosition()
                        self.setTextCursor(nc)
                    finally:
                        self._fixing_cmd_cell=False
                    e.accept()
                    return
        except Exception:
            pass
        if e.button()==Qt.MouseButton.LeftButton:
            pos=e.position().toPoint()
            cur,img,rect=self._image_handle_at(pos)
            if cur and img:
                w=img.width();h=img.height()
                if w<=0 or h<=0:
                    qimg=QImage(img.name())
                    w=qimg.width() if not qimg.isNull() else rect.width()
                    h=qimg.height() if not qimg.isNull() else rect.height()
                if w<=0 or h<=0:
                    w=h=100
                self._img_resize_active=True
                self._img_resize_pos=cur.position()
                self._img_resize_start=pos
                self._img_resize_base=(w,h)
                self._img_resize_ratio=float(w)/float(h) if h else 1.0
        super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        pos=e.position().toPoint()
        if self._img_resize_active and (e.buttons()&Qt.MouseButton.LeftButton):
            if self._img_resize_start and self._img_resize_base:
                dx=pos.x()-self._img_resize_start.x()
                dy=pos.y()-self._img_resize_start.y()
                bw,bh=self._img_resize_base
                ratio=self._img_resize_ratio if self._img_resize_ratio>0 else 1.0
                if abs(dx)>=abs(dy):
                    w=max(20,bw+dx)
                    h=max(20,int(w/ratio))
                else:
                    h=max(20,bh+dy)
                    w=max(20,int(h*ratio))
                self._apply_image_size(self._img_resize_pos,w,h)
                e.accept()
                return
        cur,img,rect=self._image_handle_at(pos)
        if cur and img:
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            try:
                cc=self.cursorForPosition(pos)
                tb=cc.currentTable()
                if tb and self._is_cmd_table(tb):
                    cell=tb.cellAt(cc)
                    if cell.isValid() and cell.column()==1:
                        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                        super().mouseMoveEvent(e)
                        return
            except Exception:
                pass
            href=self.anchorAt(pos)
            if href and (href.startswith(_CMD_ANCHOR_EDIT) or href.startswith(_CMD_ANCHOR_DEL)):
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self,e):
        if self._img_resize_active:self._img_resize_active=False
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseReleaseEvent(e)
class Widget(QWidget):
    note_saved=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("NoteWidget")
        self._saving=False
        self._dirty=False
        self._last_sig=None
        self._dbp=_db_path()
        self._notes_cache=[]
        self._note_id=None;self._orig_name=None
        self._cmd_edit_table=None
        self._toast=None;self._toast_msg=None
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("NoteFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        self.tabs=QTabWidget(self.frame);self.tabs.setObjectName("TargetTabs")
        v.addWidget(self.tabs,1)
        self.tab_create=QWidget();self.tab_create.setObjectName("Page")
        self.tab_list=QWidget();self.tab_list.setObjectName("Page")
        self.tabs.addTab(self.tab_create,"Create Note")
        self.tabs.addTab(self.tab_list,"Notes")
        self._build_create()
        self._build_list()
        self.tabs.currentChanged.connect(self._on_tab)
        QShortcut(QKeySequence("Ctrl+Shift+C"),self,activated=lambda:self._add_command(False))
        QShortcut(QKeySequence("Ctrl+S"),self,activated=lambda:self._save_note(False))
        self._toast=QFrame(self);self._toast.setObjectName("Toast");self._toast.hide()
        th=QHBoxLayout(self._toast);th.setContentsMargins(14,10,14,10);th.setSpacing(10)
        self._toast_msg=QLabel("",self._toast);self._toast_msg.setObjectName("ToastMsg")
        th.addWidget(self._toast_msg,1)
        _log("[+]",f"Note ready db={os.path.basename(self._dbp)}")
    def _build_create(self):
        v=QVBoxLayout(self.tab_create);v.setContentsMargins(0,0,0,0);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.in_name=QLineEdit(self.tab_create);self.in_name.setObjectName("NoteName");self.in_name.setPlaceholderText("Note Name");self.in_name.setMaxLength(256)
        self.btn_add=QToolButton(self.tab_create);self.btn_add.setObjectName("NoteAddCmd");self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_add.setText("Add Command")
        self.btn_clear=QToolButton(self.tab_create);self.btn_clear.setObjectName("NoteClear");self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_clear.setText("New Note")
        self.btn_save=QToolButton(self.tab_create);self.btn_save.setObjectName("NoteSave");self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_save.setText("Save")
        for b in (self.btn_add,self.btn_clear,self.btn_save):
            f=b.font();f.setBold(True);f.setWeight(900);b.setFont(f)
        self.btn_add.clicked.connect(lambda:self._add_command(False))
        self.btn_clear.clicked.connect(self._clear_note)
        self.btn_save.clicked.connect(lambda:self._save_note(True))
        top.addWidget(self.in_name,1);top.addWidget(self.btn_add,0);top.addWidget(self.btn_clear,0);top.addWidget(self.btn_save,0)
        bar=QFrame(self.tab_create);bar.setObjectName("NoteBar")
        bh=QHBoxLayout(bar);bh.setContentsMargins(14,8,14,8);bh.setSpacing(10)
        self.b_i=QToolButton(bar);self.b_i.setObjectName("FmtItalic");self.b_i.setCursor(Qt.CursorShape.PointingHandCursor);self.b_i.setText("I");self.b_i.setCheckable(True)
        self.b_b=QToolButton(bar);self.b_b.setObjectName("FmtBold");self.b_b.setCursor(Qt.CursorShape.PointingHandCursor);self.b_b.setText("B");self.b_b.setCheckable(True)
        self.b_u=QToolButton(bar);self.b_u.setObjectName("FmtUnderline");self.b_u.setCursor(Qt.CursorShape.PointingHandCursor);self.b_u.setText("U");self.b_u.setCheckable(True)
        self.font_size=QComboBox(bar);self.font_size.setObjectName("FmtFontSize")
        self.font_size.addItems(["10","12","13","14","16","18","20","22","24","28"])
        self.font_size.setCurrentText(str(int(_DEFAULT_FONT_SIZE)))
        self.font_size.setStyleSheet("QComboBox#FmtFontSize{background:#1e1e1e;border:1px solid #2b2b2b;border-radius:8px;padding:2px 8px;color:#ffffff;}QComboBox#FmtFontSize::drop-down{border:0;width:16px;}QComboBox#FmtFontSize::down-arrow{image:none;}")
        self.btn_color=QToolButton(bar);self.btn_color.setObjectName("FmtColor");self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_color.setText("Color")
        self.btn_color.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        cm=QMenu(self.btn_color)
        for name,hexv in (("Default",None),("White","#ffffff"),("Blue","#4dabf7"),("Green","#8ce99a"),("Yellow","#ffd43b"),("Orange","#ff922b"),("Red","#ff6b6b"),("Purple","#b197fc")):
            a=QAction(name,self.btn_color);a.triggered.connect(lambda chk=False,v=hexv:self._set_text_color(v));cm.addAction(a)
        self.btn_color.setMenu(cm)
        self.align_left=QToolButton(bar);self.align_left.setObjectName("FmtAlignLeft");self.align_left.setCursor(Qt.CursorShape.PointingHandCursor)
        self.align_center=QToolButton(bar);self.align_center.setObjectName("FmtAlignCenter");self.align_center.setCursor(Qt.CursorShape.PointingHandCursor)
        il=_abs("..","Assets","left-align.png")
        if os.path.isfile(il):self.align_left.setIcon(QIcon(il));self.align_left.setIconSize(QSize(16,16))
        else:self.align_left.setText("Left")
        ic=_abs("..","Assets","center.png")
        if os.path.isfile(ic):self.align_center.setIcon(QIcon(ic));self.align_center.setIconSize(QSize(16,16))
        else:self.align_center.setText("Center")
        self.btn_img=QToolButton(bar);self.btn_img.setObjectName("FmtImage");self.btn_img.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_img.setText("Image")
        self.lst=QToolButton(bar);self.lst.setObjectName("FmtList");self.lst.setCursor(Qt.CursorShape.PointingHandCursor);self.lst.setText("List")
        self.tbl=QToolButton(bar);self.tbl.setObjectName("FmtTable");self.tbl.setCursor(Qt.CursorShape.PointingHandCursor);self.tbl.setText("Table ( C , R )")
        self.b_b.clicked.connect(self._fmt_bold)
        self.b_i.clicked.connect(self._fmt_italic)
        self.b_u.clicked.connect(self._fmt_underline)
        self.font_size.currentTextChanged.connect(self._set_font_size)
        self.align_left.clicked.connect(self._align_left)
        self.align_center.clicked.connect(self._align_center)
        self.btn_img.clicked.connect(self._insert_image)
        self.lst.clicked.connect(self._fmt_list)
        self.tbl.clicked.connect(self._fmt_table)
        self.font_size.setFixedHeight(30);self.font_size.setMinimumWidth(70)
        self.btn_color.setFixedHeight(30)
        bh.addWidget(self.b_i,0);bh.addWidget(self.b_b,0);bh.addWidget(self.b_u,0)
        bh.addSpacing(10)
        bh.addWidget(self.font_size,0);bh.addWidget(self.btn_color,0)
        bh.addSpacing(10)
        bh.addWidget(self.align_left,0);bh.addWidget(self.align_center,0)
        bh.addSpacing(10)
        bh.addWidget(self.btn_img,0);bh.addWidget(self.lst,0);bh.addWidget(self.tbl,0)
        bh.addStretch(1)
        self.cmd_box=QFrame(self.tab_create);self.cmd_box.setObjectName("CmdInlineBox");self.cmd_box.setVisible(False)
        cb=QVBoxLayout(self.cmd_box);cb.setContentsMargins(14,12,14,12);cb.setSpacing(10)
        g=QGridLayout();g.setContentsMargins(0,0,0,0);g.setHorizontalSpacing(10);g.setVerticalSpacing(10)
        self.cmd_nt=QLineEdit(self.cmd_box);self.cmd_nt.setObjectName("CmdBoxNoteTitle");self.cmd_nt.setPlaceholderText("Required")
        self.cmd_cat=DropInput("CmdBoxCategory","Required",self.cmd_box)
        self.cmd_sub=DropInput("CmdBoxSubCategory","Required",self.cmd_box)
        self.cmd_desc=QLineEdit(self.cmd_box);self.cmd_desc.setObjectName("CmdBoxDescription");self.cmd_desc.setPlaceholderText("Optional")
        self.cmd_tags=QLineEdit(self.cmd_box);self.cmd_tags.setObjectName("CmdBoxTags");self.cmd_tags.setPlaceholderText("word,word,word")
        g.addWidget(QLabel("Command Note Tittle",self.cmd_box),0,0);g.addWidget(QLabel("Category",self.cmd_box),0,1);g.addWidget(QLabel("Sub Category",self.cmd_box),0,2);g.addWidget(QLabel("Description",self.cmd_box),0,3)
        g.addWidget(self.cmd_nt,1,0);g.addWidget(self.cmd_cat,1,1);g.addWidget(self.cmd_sub,1,2);g.addWidget(self.cmd_desc,1,3)
        g.addWidget(QLabel("Tags",self.cmd_box),2,0,1,4)
        g.addWidget(self.cmd_tags,3,0,1,4)
        cb.addLayout(g)
        self.cmd_code=QTextEdit(self.cmd_box);self.cmd_code.setObjectName("CmdBoxCommand");self.cmd_code.setPlaceholderText("Enter command here...")
        cb.addWidget(self.cmd_code,1)
        b=QHBoxLayout();b.setContentsMargins(0,0,0,0);b.setSpacing(10)
        self.cmd_ins=QToolButton(self.cmd_box);self.cmd_ins.setObjectName("CmdBoxInsert");self.cmd_ins.setCursor(Qt.CursorShape.PointingHandCursor);self.cmd_ins.setText("Insert")
        self.cmd_can=QToolButton(self.cmd_box);self.cmd_can.setObjectName("CmdBoxCancel");self.cmd_can.setCursor(Qt.CursorShape.PointingHandCursor);self.cmd_can.setText("Cancel")
        for x in (self.cmd_ins,self.cmd_can):
            f=x.font();f.setBold(True);f.setWeight(900);x.setFont(f)
        self.cmd_ins.clicked.connect(self._cmd_box_insert)
        self.cmd_can.clicked.connect(self._cmd_box_hide)
        b.addStretch(1);b.addWidget(self.cmd_ins,0);b.addWidget(self.cmd_can,0);b.addStretch(1)
        cb.addLayout(b)
        self.edit=NoteEdit(self._add_command,self._heading_enter,self._on_cmd_anchor,self._is_cmd_table,self.tab_create);self.edit.setPlaceholderText("Write your notes here...")
        self._update_color_button(None)
        v.addLayout(top)
        v.addWidget(bar,0)
        v.addWidget(self.cmd_box,0)
        v.addWidget(self.edit,1)
        self.in_name.textChanged.connect(self._mark_dirty)
        self.edit.textChanged.connect(self._mark_dirty)
    def resizeEvent(self,e):
        try:super().resizeEvent(e)
        except:pass
        try:self._toast_place()
        except:pass
    def _toast_place(self):
        if not self._toast:return
        w=max(220,min(420,self.width()-40))
        self._toast.setFixedSize(w,44)
        self._toast.move((self.width()-w)//2,14)
    def _toast_show(self,msg,ms=2000):
        if not self._toast:return
        self._toast_msg.setText(str(msg))
        self._toast_place()
        self._toast.show()
        QTimer.singleShot(int(ms),self._toast.hide)
    def _new_note(self):
        try:
            if hasattr(self,"cmd_box") and self.cmd_box.isVisible():self.cmd_box.setVisible(False)
        except:pass
        try:self.in_name.blockSignals(True);self.in_name.clear();self.in_name.blockSignals(False)
        except:pass
        try:self.edit.blockSignals(True);self.edit.clear();self.edit.blockSignals(False)
        except:pass
        self._last_sig=None;self._dirty=False;self._note_id=None;self._orig_name=None
        try:self._clear_heading_format()
        except:pass
        try:self.in_name.setFocus()
        except:pass
    def _build_list(self):
        v=QVBoxLayout(self.tab_list);v.setContentsMargins(0,0,0,0);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.list_search=QLineEdit(self.tab_list);self.list_search.setObjectName("NoteAddSearch");self.list_search.setPlaceholderText("Search notes...")
        self.list_search.setMinimumHeight(30);self.list_search.setMaximumHeight(30)
        self.list_search.textChanged.connect(lambda _:self._render_list())
        top.addWidget(self.list_search,1)
        self.list_wrap=QFrame(self.tab_list);self.list_wrap.setObjectName("NoteAddTableFrame")
        tw=QVBoxLayout(self.list_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.list_tbl=QTableWidget(self.list_wrap);self.list_tbl.setObjectName("NoteAddTable")
        self.list_tbl.setColumnCount(4)
        self.list_tbl.setHorizontalHeaderLabels(["Note","Updated","#","X"])
        self.list_tbl.verticalHeader().setVisible(False)
        self.list_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.list_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_tbl.setSortingEnabled(False)
        self.list_tbl.setAlternatingRowColors(False)
        self.list_tbl.setShowGrid(True)
        self.list_tbl.cellClicked.connect(self._on_list_cell)
        self.list_tbl.cellDoubleClicked.connect(self._on_list_double)
        h=self.list_tbl.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        fh=h.font();fh.setBold(True);fh.setWeight(800);h.setFont(fh)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        self.list_tbl.setColumnWidth(2,44);self.list_tbl.setColumnWidth(3,44)
        tw.addWidget(self.list_tbl,1)
        v.addLayout(top)
        v.addWidget(self.list_wrap,1)
    def _on_tab(self,i):
        if i==1:
            try:self._cmd_box_hide()
            except:pass
            self._render_list()
        else:
            try:self._cmd_box_hide()
            except:pass
    def _mark_dirty(self,*a):self._dirty=True
    def _cursor(self):return self.edit.textCursor()
    def _merge_charfmt(self,fmt):
        c=self._cursor()
        if not c.hasSelection():c.select(QTextCursor.SelectionType.WordUnderCursor)
        c.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)
    def _merge_blockfmt(self,fmt):
        c=self._cursor()
        if not c.hasSelection():c.select(QTextCursor.SelectionType.BlockUnderCursor)
        c.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)
    def _fmt_bold(self):
        fmt=QTextCharFormat();fmt.setFontWeight(900 if self.b_b.isChecked() else 400);self._merge_charfmt(fmt)
    def _fmt_italic(self):
        fmt=QTextCharFormat();fmt.setFontItalic(bool(self.b_i.isChecked()));self._merge_charfmt(fmt)
    def _fmt_underline(self):
        fmt=QTextCharFormat();fmt.setFontUnderline(bool(self.b_u.isChecked()));self._merge_charfmt(fmt)
    def _set_font_size(self,t):
        try:size=float(t)
        except:return
        fmt=QTextCharFormat();fmt.setFontPointSize(size)
        c=self._cursor()
        if not c.hasSelection():c.select(QTextCursor.SelectionType.BlockUnderCursor)
        c.mergeCharFormat(fmt);self.edit.mergeCurrentCharFormat(fmt)
        self._dirty=True
    def _update_color_button(self,hexv):
        self._current_text_color=hexv
        if not hexv:
            self.btn_color.setText("Color")
            self.btn_color.setStyleSheet("QToolButton#FmtColor{background:#ffffff;color:#000000;border:1px solid #2b2b2b;border-radius:8px;padding:2px 8px;}")
            return
        h=hexv.lstrip("#")
        try:
            r=int(h[0:2],16);g=int(h[2:4],16);b=int(h[4:6],16)
        except:
            r=g=b=255
        lum=(0.299*r+0.587*g+0.114*b)/255.0
        fg="#000000" if lum>0.6 else "#ffffff"
        self.btn_color.setText("Color")
        self.btn_color.setStyleSheet(f"QToolButton#FmtColor{{background:{hexv};color:{fg};border:1px solid #2b2b2b;border-radius:8px;padding:2px 8px;}}")
    def _set_text_color(self,hexv):
        fmt=QTextCharFormat()
        if hexv:fmt.setForeground(QColor(hexv))
        else:fmt.clearForeground()
        self._merge_charfmt(fmt);self._dirty=True
        self._update_color_button(hexv)
    def _align_left(self):
        c=self._cursor()
        if not c.hasSelection():c.select(QTextCursor.SelectionType.BlockUnderCursor)
        fmt=QTextBlockFormat();fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        c.mergeBlockFormat(fmt);self.edit.setTextCursor(c);self._dirty=True
    def _align_center(self):
        c=self._cursor()
        if not c.hasSelection():c.select(QTextCursor.SelectionType.BlockUnderCursor)
        fmt=QTextBlockFormat();fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        c.mergeBlockFormat(fmt);self.edit.setTextCursor(c);self._dirty=True
    def _insert_image(self):
        p,_=QFileDialog.getOpenFileName(self,"Insert Image",_abs(".."),"Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)")
        if not p:return
        img=QImage(p)
        iw=img.width() if not img.isNull() else 320
        ih=img.height() if not img.isNull() else 240
        def_w=min(iw,640) if iw>0 else 320
        def_h=int((ih*def_w)/iw) if iw>0 and ih>0 else min(ih,480)
        w,ok=QInputDialog.getInt(self,"Image Width","Width (px):",int(def_w),20,4000,10)
        if not ok:return
        h,ok=QInputDialog.getInt(self,"Image Height","Height (px):",int(def_h if def_h>0 else w),20,4000,10)
        if not ok:return
        cur=self._cursor()
        fmt=QTextImageFormat();fmt.setName(p);fmt.setWidth(float(w));fmt.setHeight(float(h))
        cur.insertImage(fmt);self.edit.setTextCursor(cur);self._dirty=True
    def _clear_heading_format(self):
        fmt=QTextCharFormat();fmt.setFontPointSize(_DEFAULT_FONT_SIZE);fmt.setFontWeight(400);self._merge_blockfmt(fmt)
        try:
            self.font_size.blockSignals(True)
            self.font_size.setCurrentText(str(int(_DEFAULT_FONT_SIZE)))
            self.font_size.blockSignals(False)
        except:pass
    def _heading_enter(self):
        return
    def _apply_code_style(self,start,end):
        if start is None or end is None or start>=end:return
        c=QTextCursor(self.edit.document())
        c.setPosition(int(start))
        c.setPosition(int(end),QTextCursor.MoveMode.KeepAnchor)
        fmt=QTextCharFormat();fmt.setForeground(QColor(_CODE_COLOR));fmt.setFontFamily(_CODE_FONT);fmt.setFontFixedPitch(True)
        c.mergeCharFormat(fmt)
    def _fmt_list(self):
        c=self._cursor()
        lf=QTextListFormat();lf.setStyle(QTextListFormat.Style.ListDisc);lf.setIndent(1)
        c.insertList(lf);self.edit.setTextCursor(c);self._dirty=True
    def _fmt_table(self):
        d=_TableDlg(self.window() if self.window() else self)
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):d.setWindowIcon(QIcon(ico))
        if d.exec()!=QDialog.DialogCode.Accepted:return
        r,c=d.vals()
        cur=self._cursor()
        tf=QTextTableFormat();tf.setCellPadding(4);tf.setCellSpacing(1);tf.setBorder(1)
        cur.insertTable(r,c,tf);self.edit.setTextCursor(cur);self._dirty=True
    def _cmd_data(self,nt,cat,sub,desc,tags,cmd):
        return {
            "cmd_note_title":_norm(nt),
            "category":_norm(cat),
            "sub_category":_norm(sub),
            "description":_norm(desc),
            "tags":_norm(tags),
            "command":(cmd or "").rstrip(),
        }
    def _iter_tables(self):
        doc=self.edit.document()
        cur=QTextCursor(doc)
        cur.movePosition(QTextCursor.MoveOperation.Start)
        tables=[]
        seen=set()
        while not cur.atEnd():
            tb=cur.currentTable()
            if tb:
                tid=id(tb)
                if tid not in seen:
                    seen.add(tid);tables.append(tb)
                try:
                    cur.setPosition(tb.lastCursorPosition().position()+1)
                except Exception:
                    cur.movePosition(QTextCursor.MoveOperation.NextBlock)
                continue
            cur.movePosition(QTextCursor.MoveOperation.NextBlock)
        return tables
    def _find_cmd_anchor_in_table(self,table):
        if not table:return ""
        try:
            for r in range(table.rows()):
                for c in range(table.columns()):
                    cell=table.cellAt(r,c)
                    cur=cell.firstCursorPosition()
                    end=cell.lastCursorPosition().position()
                    blk=cur.block()
                    while blk.isValid() and blk.position()<=end:
                        it=blk.begin()
                        while not it.atEnd():
                            frag=it.fragment()
                            if not frag.isValid():
                                it+=1;continue
                            fmt=frag.charFormat()
                            if fmt.isAnchor():
                                href=fmt.anchorHref()
                                if href.startswith(_CMD_ANCHOR_EDIT):
                                    return href[len(_CMD_ANCHOR_EDIT):]
                            it+=1
                        blk=blk.next()
        except Exception:
            return ""
        return ""
    def _is_cmd_table(self,table):
        if not table:return False
        try:
            if _norm(table.format().property(_CMD_TABLE_PROP)):return True
        except Exception:
            pass
        return bool(self._find_cmd_anchor_in_table(table))
    def _cmd_data_from_table(self,table):
        if not table:return {}
        token=""
        try:token=_norm(table.format().property(_CMD_TABLE_PROP))
        except Exception:token=""
        if not token:token=self._find_cmd_anchor_in_table(table)
        return _decode_cmd_data(token)
    def _apply_cmd_table_style(self,table):
        if not table:return
        tf=table.format()
        tf.setBorder(1);tf.setCellPadding(6);tf.setCellSpacing(0)
        try:
            tf.setWidth(QTextLength(QTextLength.Type.PercentageLength,100))
            tf.setColumnWidthConstraints([
                QTextLength(QTextLength.Type.PercentageLength,100),
                QTextLength(QTextLength.Type.FixedLength,70),
            ])
        except Exception:
            pass
        table.setFormat(tf)
        bg=QColor("#1e1e1e")
        for r in range(table.rows()):
            for c in range(table.columns()):
                cell=table.cellAt(r,c)
                cf=cell.format();cf.setBackground(bg);cell.setFormat(cf)
    def _render_cmd_controls(self,cell,token):
        if not cell or not token:return
        c2=cell.firstCursorPosition()
        c2.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
        c2.removeSelectedText()
        bf=QTextBlockFormat();bf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:bf.setNonBreakableLines(True)
        except Exception:pass
        c2.mergeBlockFormat(bf)
        a_fmt=QTextCharFormat();a_fmt.setAnchor(True);a_fmt.setAnchorHref(_CMD_ANCHOR_EDIT+token);a_fmt.setForeground(QColor("#6bb6ff"));a_fmt.setFontWeight(800)
        d_fmt=QTextCharFormat();d_fmt.setAnchor(True);d_fmt.setAnchorHref(_CMD_ANCHOR_DEL+token);d_fmt.setForeground(QColor("#ff6b6b"));d_fmt.setFontWeight(800)
        sp_fmt=QTextCharFormat()
        c2.insertText("#",a_fmt)
        c2.insertText("  ",sp_fmt)
        c2.insertText("X",d_fmt)
    def _insert_cmd_table(self,data,cursor=None):
        d=dict(data or {})
        if not d.get("command"):return None
        token=_encode_cmd_data(d)
        cur=cursor if cursor is not None else self.edit.textCursor()
        tf=QTextTableFormat();tf.setCellPadding(6);tf.setCellSpacing(0);tf.setBorder(1)
        tf.setProperty(_CMD_TABLE_PROP,token)
        table=cur.insertTable(1,2,tf)
        self._apply_cmd_table_style(table)
        cmd_fmt=QTextCharFormat();cmd_fmt.setForeground(QColor(_CODE_COLOR));cmd_fmt.setFontFamily(_CODE_FONT);cmd_fmt.setFontFixedPitch(True)
        cell=table.cellAt(0,0)
        c=cell.firstCursorPosition()
        c.insertText(d.get("command",""),cmd_fmt)
        cell2=table.cellAt(0,1)
        self._render_cmd_controls(cell2,token)
        cur=table.lastCursorPosition()
        try:
            cur.movePosition(QTextCursor.MoveOperation.NextBlock)
            if cur.currentTable() is table:
                cur=QTextCursor(self.edit.document())
                cur.setPosition(table.lastCursorPosition().position()+1)
        except Exception:
            pass
        self.edit.setTextCursor(cur)
        return table
    def _update_cmd_table(self,table,data):
        if not table:return
        d=dict(data or {})
        if not d.get("command"):d["command"]=""
        token=_encode_cmd_data(d)
        tf=table.format();tf.setProperty(_CMD_TABLE_PROP,token);table.setFormat(tf)
        self._apply_cmd_table_style(table)
        cmd_fmt=QTextCharFormat();cmd_fmt.setForeground(QColor(_CODE_COLOR));cmd_fmt.setFontFamily(_CODE_FONT);cmd_fmt.setFontFixedPitch(True)
        cell=table.cellAt(0,0)
        c=cell.firstCursorPosition()
        c.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        c.insertText(d.get("command",""),cmd_fmt)
        cell2=table.cellAt(0,1)
        self._render_cmd_controls(cell2,token)
    def _delete_cmd_table(self,table):
        if not table:return
        try:
            cur=table.firstCursorPosition()
            cur.select(QTextCursor.SelectionType.TableUnderCursor)
            cur.removeSelectedText()
            cur.deleteChar()
        except Exception:
            pass
    def _extract_cmds_from_doc(self):
        cmds=[]
        seen=set()
        for tb in self._iter_tables():
            if not self._is_cmd_table(tb):continue
            d=self._cmd_data_from_table(tb)
            if not d:continue
            cid=_norm(d.get("cid",""))
            if cid and cid in seen:continue
            if cid:seen.add(cid)
            cmds.append(d)
        return cmds
    def _convert_cmd_blocks(self,mark_dirty=False):
        text=self.edit.toPlainText()
        matches=[]
        for m in re.finditer(r"<C\s*\[(.*?)\]\s*>\s*(.*?)\s*</C>",text,re.S|re.I):
            meta=(m.group(1) or "").strip()
            body=(m.group(2) or "").rstrip()
            if not _norm(body):continue
            data=_parse_cmd_meta(meta)
            data["command"]=body
            if not _norm(data.get("cmd_note_title","")):
                data["cmd_note_title"]=_norm(self.in_name.text())
            matches.append((m.start(),m.end(),data))
        if not matches:return
        cur=self.edit.textCursor()
        for start,end,data in reversed(matches):
            cur.setPosition(start)
            cur.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
            self._insert_cmd_table(data,cur)
        if mark_dirty:self._dirty=True
    def _bind_cmd_tables_from_anchors(self):
        for tb in self._iter_tables():
            try:
                if _norm(tb.format().property(_CMD_TABLE_PROP)):continue
            except Exception:
                pass
            token=self._find_cmd_anchor_in_table(tb)
            if not token:continue
            tf=tb.format();tf.setProperty(_CMD_TABLE_PROP,token);tb.setFormat(tf)
            self._apply_cmd_table_style(tb)
            try:
                cell2=tb.cellAt(0,1)
                if cell2.isValid():self._render_cmd_controls(cell2,token)
            except Exception:
                pass
    def _open_cmd_editor(self,data,table):
        self._cmd_cursor=self.edit.textCursor()
        self._cmd_edit_table=table
        self.cmd_nt.setText(_norm(data.get("cmd_note_title","")) or _norm(self.in_name.text()))
        self.cmd_desc.setText(_norm(data.get("description","")))
        self.cmd_tags.setText(_norm(data.get("tags","")))
        self.cmd_code.setPlainText(_norm(data.get("command","")))
        cats,subs=_cmd_meta(self._dbp)
        self.cmd_cat.set_items(cats,"Type a Category");self.cmd_cat.setText(_norm(data.get("category","")))
        self.cmd_sub.set_items([],"Type a Sub Category");self.cmd_sub.setText(_norm(data.get("sub_category","")))
        def _subs_for(cat):
            c=_norm(cat)
            if not c:return []
            if c in subs:return subs[c]
            lc=c.lower()
            for k,v in subs.items():
                kl=k.lower()
                if kl==lc or kl.startswith(lc):return v
            return []
        def _sync_sub():
            self.cmd_sub.set_items(_subs_for(self.cmd_cat.text()),"Type a Sub Category")
        le=self.cmd_cat.lineEdit()
        try:le.textChanged.disconnect()
        except:pass
        le.textChanged.connect(lambda _=None:_sync_sub())
        _sync_sub()
        try:self.cmd_ins.setText("Update")
        except Exception:pass
        self.cmd_box.setVisible(True)
        try:le.setFocus()
        except:self.cmd_cat.setFocus()
    def _on_cmd_anchor(self,href,cursor):
        action="edit" if href.startswith(_CMD_ANCHOR_EDIT) else ("delete" if href.startswith(_CMD_ANCHOR_DEL) else "")
        if not action:return
        token=href.split(":",1)[1] if ":" in href else ""
        data=_decode_cmd_data(token)
        table=cursor.currentTable()
        if not self._is_cmd_table(table):return
        if action=="delete":
            w=self.window() if self.window() else self
            msg="Delete this command box? You can undo."
            if QMessageBox.question(w,"Delete Command",msg,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
                return
            self._delete_cmd_table(table);self._dirty=True
            return
        if not data:data=self._cmd_data_from_table(table)
        self._open_cmd_editor(data,table)
    def _cmd_template(self,nt,cat,sub,desc,tags,cmd):
        nt=_norm(nt) or "Required"
        cat=_norm(cat) or "Required"
        sub=_norm(sub) or "Required"
        desc=_norm(desc) or "Optional"
        tags=_norm(tags) or "word,word,word"
        cmd=(cmd or "").rstrip()
        if not cmd:cmd="Enter command here..."
        return f"<C [Command Note Tittle:{nt}, Category:{cat}, Sub Category:{sub}, Description:{desc}, Tags:{tags}] >\n{cmd}\n</C>\n"
    def _add_command(self,from_menu):
        self._cmd_cursor=self.edit.textCursor()
        self._cmd_edit_table=None
        nt=_norm(self.in_name.text());self.cmd_nt.setText(nt)
        self.cmd_desc.setText("");self.cmd_tags.setText("");self.cmd_code.setPlainText("")
        cats,subs=_cmd_meta(self._dbp)
        self.cmd_cat.set_items(cats,"Type a Category");self.cmd_cat.setText("")
        self.cmd_sub.set_items([],"Type a Sub Category");self.cmd_sub.setText("")
        def _subs_for(cat):
            c=_norm(cat)
            if not c:return []
            if c in subs:return subs[c]
            lc=c.lower()
            for k,v in subs.items():
                kl=k.lower()
                if kl==lc or kl.startswith(lc):return v
            return []
        def _sync_sub():
            self.cmd_sub.set_items(_subs_for(self.cmd_cat.text()),"Type a Sub Category")
        le=self.cmd_cat.lineEdit()
        try:le.textChanged.disconnect()
        except:pass
        le.textChanged.connect(lambda _=None:_sync_sub())
        _sync_sub()
        try:self.cmd_ins.setText("Insert")
        except Exception:pass
        self.cmd_box.setVisible(True)
        try:le.setFocus()
        except:self.cmd_cat.setFocus()
        _log("[*]","Add command box opened")
    def _cmd_box_hide(self):
        if hasattr(self,"cmd_box") and self.cmd_box.isVisible():self.cmd_box.setVisible(False)
        self._cmd_edit_table=None
        try:self.cmd_ins.setText("Insert")
        except Exception:pass
        try:self.edit.setFocus()
        except:pass
    def _cmd_box_insert(self):
        data=self._cmd_data(self.cmd_nt.text(),self.cmd_cat.text(),self.cmd_sub.text(),self.cmd_desc.text(),self.cmd_tags.text(),self.cmd_code.toPlainText())
        if self._cmd_edit_table:
            self._update_cmd_table(self._cmd_edit_table,data)
            self._cmd_edit_table=None
        else:
            try:c=self._cmd_cursor if getattr(self,"_cmd_cursor",None) else self.edit.textCursor()
            except:c=self.edit.textCursor()
            self._insert_cmd_table(data,c)
        self._dirty=True
        if hasattr(self,"cmd_box"):self.cmd_box.setVisible(False)
        try:self.edit.setFocus()
        except:pass
        _log("[*]","Add command inserted")
    def _clear_note(self):
        w=self.window() if self.window() else self
        name=_norm(self.in_name.text())
        body=_norm(self.edit.toPlainText())
        if not name and not body and not self._dirty:self._new_note();return
        if QMessageBox.question(w,"New Note","Start a new note? Unsaved changes will be lost.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self._new_note()
        _log("[*]","New note started")
    def _load_into_editor(self,n):
        self._cmd_box_hide()
        name=(n.get("note_name","") or "").strip()
        htmls=n.get("content","") or ""
        self._note_id=n.get("id",None);self._orig_name=name
        self.in_name.setText(name)
        self.edit.blockSignals(True)
        self.edit.setHtml(htmls)
        has_c=("<C [" in htmls) or ("<c [" in htmls) or ("&lt;C [" in htmls) or ("&lt;c [" in htmls)
        has_anchor=(_CMD_ANCHOR_EDIT in htmls) or (_CMD_ANCHOR_DEL in htmls)
        if has_c:self._convert_cmd_blocks(mark_dirty=False)
        if has_anchor:self._bind_cmd_tables_from_anchors()
        self.edit.blockSignals(False)
        self._last_sig=_sig(name,htmls)
        self._dirty=False
        self._clear_heading_format()
        self.tabs.setCurrentIndex(0)
        _log("[*]",f"Loaded note: {name}")
    def _render_list(self):
        self._notes_cache=_load_notes(self._dbp)
        q=_norm(self.list_search.text()).lower()
        rows=[]
        for n in self._notes_cache:
            nm=(n.get("note_name","") or "");up=(n.get("updated_at","") or "")
            if q and q not in (nm+" "+up).lower():continue
            rows.append(n)
        self.list_tbl.setRowCount(len(rows))
        for r,n in enumerate(rows):
            nm=QTableWidgetItem((n.get("note_name","") or "").strip());nm.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);nm.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            fn=nm.font();fn.setBold(True);fn.setWeight(800);nm.setFont(fn);nm.setData(Qt.ItemDataRole.UserRole,n)
            up=QTableWidgetItem((n.get("updated_at","") or "").replace("T"," ")[:19]);up.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);up.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ed=QTableWidgetItem("#");ed.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);ed.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            xd=QTableWidgetItem("X");xd.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);xd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fe=ed.font();fe.setBold(True);fe.setWeight(800);ed.setFont(fe);xd.setFont(fe)
            self.list_tbl.setItem(r,0,nm);self.list_tbl.setItem(r,1,up);self.list_tbl.setItem(r,2,ed);self.list_tbl.setItem(r,3,xd)
            self.list_tbl.setRowHeight(r,44)
        self.list_tbl.clearSelection()
    def _row_note(self,row):
        it=self.list_tbl.item(row,0)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _on_list_cell(self,row,col):
        n=self._row_note(row)
        if not n:return
        if col in (0,1,2):return self._load_into_editor(n)
        if col==3:
            w=self.window() if self.window() else self
            name=(n.get("note_name","") or "").strip()
            if QMessageBox.question(w,"Delete",f"Delete note: {name}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            ok=_delete_note(self._dbp,name)
            if ok:self._render_list();_log("[+]",f"Deleted note: {name}")
            else:QMessageBox.critical(w,"Error","Failed to delete note.")
    def _on_list_double(self,row,col):
        n=self._row_note(row)
        if n:self._load_into_editor(n)
    def _save_note(self,reset_after):
        if self._saving:return False
        self._saving=True
        self.btn_save.setEnabled(False);self.btn_clear.setEnabled(False);self.btn_add.setEnabled(False)
        try:
            name=_norm(self.in_name.text())
            if not name:
                w=self.window() if self.window() else self
                QMessageBox.warning(w,"Missing","Note Name is required.")
                return False
            htmls=self.edit.toHtml()
            plain=self.edit.toPlainText()
            cmds=self._extract_cmds_from_doc()
            if not cmds:
                cmds=_parse_cmd_blocks(plain)
            if not _norm(plain):
                w=self.window() if self.window() else self
                QMessageBox.warning(w,"Missing","Note area is empty.")
                return False
            sig=_sig(name,htmls)
            if self._last_sig==sig and not self._dirty:
                self._toast_show("Already saved",1500)
                _log("[*]",f"Save skipped (already saved): {name}")
                return True
            dbp=self._dbp or _db_path()
            now=datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(dbp,timeout=5) as con:
                _ensure_schema(con);_ensure_cmd_schema(con)
                cur=con.cursor()
                if self._note_id:
                    cur.execute("UPDATE Notes SET note_name=?,content=?,updated_at=? WHERE id=?",(name,htmls,now,int(self._note_id)))
                    nid=int(self._note_id)
                    action="update"
                else:
                    cur.execute("SELECT id FROM Notes WHERE note_name=?",(name,))
                    exists=cur.fetchone()
                    cur.execute("INSERT INTO Notes(note_name,content,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(note_name) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at",(name,htmls,now,now))
                    cur.execute("SELECT id FROM Notes WHERE note_name=?",(name,));r=cur.fetchone()
                    nid=int(r[0]) if r else None
                    self._note_id=nid
                    action="update" if exists else "insert"
                _insert_note_history(cur,nid,name,htmls,action,now)
                ncmd=_sync_commands(con,nid,name,cmds,now) if nid else 0
            self._orig_name=name
            self._last_sig=sig
            self._dirty=False
            try:self.note_saved.emit()
            except:pass
            try:self._render_list()
            except:pass
            self._toast_show(f"Saved ({ncmd})",2000)
            if reset_after:QTimer.singleShot(2000,self._new_note)
            _log("[+]",f"Saved note: {name} cmds={ncmd}")
            return True
        except Exception as e:
            _log("[!]",f"Save failed ({e})")
            w=self.window() if self.window() else self
            QMessageBox.critical(w,"Error","Failed to save note.")
            return False
        finally:
            self._saving=False
            self.btn_save.setEnabled(True);self.btn_clear.setEnabled(True);self.btn_add.setEnabled(True)
    def open_note_by_name(self,name):
        nm=_norm(name)
        if not nm:return False
        try:
            self._notes_cache=_load_notes(self._dbp)
        except Exception:
            self._notes_cache=[]
        for n in self._notes_cache:
            if _norm(n.get("note_name","")).lower()==nm.lower():
                try:
                    self._load_into_editor(n)
                    self.tabs.setCurrentWidget(self.tab_create)
                    return True
                except Exception:
                    return False
        return False
    def open_note_by_id(self,nid):
        try:tid=int(nid)
        except Exception:return False
        try:
            self._notes_cache=_load_notes(self._dbp)
        except Exception:
            self._notes_cache=[]
        for n in self._notes_cache:
            try:
                if int(n.get("id"))==tid:
                    self._load_into_editor(n)
                    self.tabs.setCurrentWidget(self.tab_create)
                    return True
            except Exception:
                continue
        return False
    def create_note_prefill(self,name="",content=""):
        before_name=_norm(self.in_name.text())
        before_body=self.edit.toPlainText()
        before_id=self._note_id
        before_dirty=self._dirty
        self._clear_note()
        after_name=_norm(self.in_name.text())
        after_body=self.edit.toPlainText()
        after_id=self._note_id
        after_dirty=self._dirty
        if (before_name or before_body or before_dirty) and after_name==before_name and after_body==before_body and after_id==before_id and after_dirty==before_dirty:
            return False
        nm=_norm(name)
        if nm:self.in_name.setText(nm)
        if content is not None:
            txt=str(content)
            if txt:
                try:self.edit.setPlainText(txt)
                except Exception:pass
        self._dirty=True
        return True
