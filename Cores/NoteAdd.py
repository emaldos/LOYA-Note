import os,sqlite3,logging
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QSize,QTimer,pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QToolButton,QHeaderView,QComboBox,QMessageBox
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("NoteAdd");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"NoteAdd_log.log"))
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
def _db_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"Note_LOYA_V1.db")
DB_SCHEMA_VERSION=2
def _ensure_schema(con):
    cur=con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS Notes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT UNIQUE,content TEXT,created_at TEXT,updated_at TEXT)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_name ON Notes(note_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated ON Notes(updated_at)")
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
def _norm(s):return " ".join((s or "").strip().split())
def _dt(s):
    t=_norm(s)
    if not t:return ""
    t=t.replace("T"," ")
    return t[:19] if len(t)>=19 else t
def _insert_note_history(cur,note_id,note_name,content,action,action_at):
    try:
        cur.execute("INSERT INTO NotesHistory(note_id,note_name,content,action,action_at) VALUES(?,?,?,?,?)",(note_id,note_name,content,action,action_at))
    except:pass
def _load_notes(dbp):
    if not dbp:dbp=_db_path()
    try:
        con=sqlite3.connect(dbp);_ensure_schema(con)
        cur=con.cursor()
        cur.execute("SELECT id,note_name,created_at,updated_at FROM Notes ORDER BY COALESCE(updated_at,created_at) DESC,id DESC")
        rows=cur.fetchall();con.close()
        out=[]
        for r in rows:
            out.append({"id":r[0],"note_name":_norm(r[1]) or "Untitled","created_at":_dt(r[2]),"updated_at":_dt(r[3]),"db":dbp})
        _log("[+]",f"Loaded notes: {len(out)} from {os.path.basename(dbp)}")
        return dbp,out
    except Exception as e:
        _log("[!]",f"Load error ({e})")
        return dbp,[]
def _get_note(dbp,nid):
    if not dbp or nid is None:return None
    try:
        con=sqlite3.connect(dbp);_ensure_schema(con)
        cur=con.cursor()
        cur.execute("SELECT id,note_name,content,created_at,updated_at FROM Notes WHERE id=?",(int(nid),))
        r=cur.fetchone();con.close()
        if not r:return None
        return {"id":r[0],"note_name":_norm(r[1]) or "Untitled","content":r[2] or "","created_at":_dt(r[3]),"updated_at":_dt(r[4]),"db":dbp}
    except Exception as e:
        _log("[!]",f"Get note error ({e})")
        return None
def _delete_note(dbp,nid):
    if not dbp or nid is None:return False
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con)
            cur=con.cursor()
            now=datetime.now(timezone.utc).isoformat()
            try:
                cur.execute("SELECT id,note_name,content FROM Notes WHERE id=?",(int(nid),))
                r=cur.fetchone()
                if r:_insert_note_history(cur,r[0],r[1] or "",r[2] or "","delete",now)
            except:pass
            cur.execute("DELETE FROM Notes WHERE id=?",(int(nid),))
            con.commit()
            return bool(cur.rowcount)
    except Exception as e:
        _log("[!]",f"Delete error ({e})")
        return False
class Widget(QWidget):
    note_open=pyqtSignal(dict)
    note_deleted=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("NoteAddWidget")
        self._dbp=_db_path()
        self._notes=[]
        self._view=[]
        self._page=1
        self._per=10
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("NoteAddFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.search=QLineEdit(self.frame);self.search.setObjectName("NoteAddSearch");self.search.setPlaceholderText("Search notes by name...")
        self.search.textChanged.connect(self._on_search)
        self.btn_refresh=QToolButton(self.frame);self.btn_refresh.setObjectName("NoteAddRefresh");self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_refresh.setText("Refresh")
        f=self.btn_refresh.font();f.setBold(True);f.setWeight(800);self.btn_refresh.setFont(f)
        self.btn_refresh.clicked.connect(self.reload)
        top.addWidget(self.search,1);top.addWidget(self.btn_refresh,0)
        self.tbl_wrap=QFrame(self.frame);self.tbl_wrap.setObjectName("NoteAddTableFrame")
        tw=QVBoxLayout(self.tbl_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.table=QTableWidget(self.tbl_wrap);self.table.setObjectName("NoteAddTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Note Name","Date Created","Updated","#","X"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.cellClicked.connect(self._on_cell_click)
        self.table.cellDoubleClicked.connect(self._on_cell_double)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        fh=h.font();fh.setBold(True);fh.setWeight(800);h.setFont(fh)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3,44);self.table.setColumnWidth(4,44)
        tw.addWidget(self.table,1)
        self.pager=QFrame(self.tbl_wrap);self.pager.setObjectName("NoteAddPagerFrame")
        ph=QHBoxLayout(self.pager);ph.setContentsMargins(0,0,0,0);ph.setSpacing(10)
        self.lbl_total=QLabel("",self.pager);self.lbl_total.setObjectName("NoteAddTotal")
        mid=QHBoxLayout();mid.setContentsMargins(0,0,0,0);mid.setSpacing(8)
        self.btn_prev=QToolButton(self.pager);self.btn_prev.setObjectName("NoteAddPrev");self.btn_prev.setText("<");self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next=QToolButton(self.pager);self.btn_next.setObjectName("NoteAddNext");self.btn_next.setText(">");self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_page=QLabel("0 of 0",self.pager);self.lbl_page.setObjectName("NoteAddPage");self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next.clicked.connect(self._next_page)
        mid.addWidget(self.btn_prev,0);mid.addWidget(self.lbl_page,0);mid.addWidget(self.btn_next,0)
        right=QHBoxLayout();right.setContentsMargins(0,0,0,0);right.setSpacing(8)
        self.cmb_per=QComboBox(self.pager);self.cmb_per.setObjectName("NoteAddPerPage")
        self.cmb_per.addItems(["10","20","50","100"]);self.cmb_per.setCurrentText("10")
        self.cmb_per.currentTextChanged.connect(self._on_per_page)
        self.lbl_per=QLabel("per page",self.pager);self.lbl_per.setObjectName("NoteAddPerLbl")
        right.addWidget(self.cmb_per,0);right.addWidget(self.lbl_per,0)
        ph.addWidget(self.lbl_total,0);ph.addStretch(1);ph.addLayout(mid,0);ph.addStretch(1);ph.addLayout(right,0)
        tw.addWidget(self.pager,0)
        v.addLayout(top)
        v.addWidget(self.tbl_wrap,1)
        QTimer.singleShot(0,self.reload)
        _log("[+]",f"NoteAdd ready db={os.path.basename(self._dbp)}")
    def reload(self):
        self._dbp,self._notes=_load_notes(self._dbp)
        self._page=1
        self._apply()
    def _apply(self):
        q=_norm(self.search.text()).lower()
        if not q:self._view=list(self._notes)
        else:self._view=[n for n in self._notes if q in (n.get("note_name","").lower())]
        self._render()
    def _pages(self):
        n=len(self._view);per=max(1,int(self._per))
        return max(1,(n+per-1)//per)
    def _slice(self):
        per=max(1,int(self._per))
        a=(self._page-1)*per
        b=a+per
        return self._view[a:b]
    def _render(self):
        tot=len(self._view);pg=self._pages()
        if self._page>pg:self._page=pg
        if self._page<1:self._page=1
        self.lbl_total.setText(f"Total: {tot}")
        self.lbl_page.setText(f"{self._page} of {pg}")
        rows=self._slice()
        self.table.setRowCount(len(rows))
        for r,n in enumerate(rows):self._set_row(r,n)
        self.table.clearSelection()
    def _set_item(self,row,col,text,full=None,align=None,bold=False):
        it=QTableWidgetItem(text)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
        if align is not None:it.setTextAlignment(align)
        if bold:
            f=it.font();f.setBold(True);f.setWeight(800);it.setFont(f)
        if full is not None:it.setData(Qt.ItemDataRole.UserRole,full)
        self.table.setItem(row,col,it)
    def _set_row(self,r,n):
        self._set_item(r,0,n.get("note_name",""),n,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,True)
        self._set_item(r,1,n.get("created_at",""),None,Qt.AlignmentFlag.AlignCenter)
        self._set_item(r,2,n.get("updated_at",""),None,Qt.AlignmentFlag.AlignCenter)
        self._set_item(r,3,"#",None,Qt.AlignmentFlag.AlignCenter,True)
        self._set_item(r,4,"X",None,Qt.AlignmentFlag.AlignCenter,True)
        self.table.setRowHeight(r,44)
    def _row_note(self,row):
        it=self.table.item(row,0)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _prev_page(self):
        if self._page>1:self._page-=1;self._render()
    def _next_page(self):
        if self._page<self._pages():self._page+=1;self._render()
    def _on_per_page(self,t):
        try:self._per=max(1,int(t))
        except:self._per=10
        self._page=1
        self._render()
    def _on_search(self,t):
        self._page=1
        self._apply()
    def _open_note(self,n):
        item=_get_note(n.get("db"),n.get("id"))
        if not item:return
        try:self.note_open.emit(item)
        except:pass
    def _on_cell_click(self,row,col):
        n=self._row_note(row)
        if not n:return
        if col==3:
            self._open_note(n)
            return
        if col==4:
            w=self.window() if self.window() else self
            if QMessageBox.question(w,"Delete",f"Delete note: {n.get('note_name','')}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            ok=_delete_note(n.get("db"),n.get("id"))
            if ok:
                _log("[+]",f"Deleted note: {n.get('note_name','')}")
                try:self.note_deleted.emit()
                except:pass
                self.reload()
            else:
                _log("[-]",f"Delete failed: {n.get('note_name','')}")
                QMessageBox.critical(w,"Error","Failed to delete note.")
    def _on_cell_double(self,row,col):
        n=self._row_note(row)
        if not n:return
        self._open_note(n)
