import os,sqlite3,logging,json,re,html
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QTimer,QPoint
from PyQt6.QtGui import QAction,QFontMetrics
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLineEdit,QComboBox,QToolButton,QStackedWidget,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QMenu,QApplication,QSizePolicy,QListWidget,QListWidgetItem,QSplitter,QLabel,QInputDialog,QMessageBox
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("SearchCore");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"SearchCore_log.log"))
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
def _norm(s):return (str(s) if s is not None else "").strip()
def _l(s):return _norm(s).lower()
def _ell(s,n):
    s=_norm(s)
    if not s:return ""
    return (s[:max(0,n-3)]+"...") if len(s)>n else s
def _clean_cmd(s):
    raw=html.unescape(str(s or ""))
    low=raw.lower()
    if "<span" in low or "<pre" in low or "<p" in low or "<div" in low or "<br" in low or "style=" in low or "-qt-" in low:
        raw=re.sub(r"<[^>]+>"," ",raw)
    raw=raw.replace("\xa0"," ")
    raw=re.sub(r"[ \t\r\f\v]+"," ",raw)
    raw=re.sub(r"\n\s+","\n",raw)
    raw=re.sub(r"\s+\n","\n",raw)
    return raw.strip()
def _safe_mtime(p):
    try:return os.path.getmtime(p) if p and os.path.isfile(p) else None
    except:return None
def _db_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"Note_LOYA_V1.db")
DB_SCHEMA_VERSION=2
def _table_cols(cur,t):
    try:cur.execute(f"PRAGMA table_info({t})");return [r[1] for r in cur.fetchall()]
    except:return []
def _ensure_schema(con):
    try:
        con.execute("CREATE TABLE IF NOT EXISTS CommandsNotes(id INTEGER PRIMARY KEY AUTOINCREMENT,note_name TEXT,category TEXT,sub_category TEXT,command TEXT,tags TEXT,description TEXT,created_at TEXT,updated_at TEXT)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_note_name ON CommandsNotes(note_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_category ON CommandsNotes(category)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmdn_sub_category ON CommandsNotes(sub_category)")
    except:pass
    try:
        con.execute("CREATE TABLE IF NOT EXISTS Commands(id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER,note_name TEXT,cmd_note_title TEXT,category TEXT,sub_category TEXT,description TEXT,tags TEXT,command TEXT,created_at TEXT,updated_at TEXT)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmd_note_id ON Commands(note_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmd_note_name ON Commands(note_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmd_category ON Commands(category)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_cmd_sub_category ON Commands(sub_category)")
    except:pass
    _apply_migrations(con)
    try:con.commit()
    except:pass
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
def _load_cmds(dbp=None):
    p=dbp or _db_path()
    if not p or not os.path.isfile(p):
        _log("[-]",f"DB not found: {p}")
        return p,[]
    try:
        con=sqlite3.connect(p);_ensure_schema(con)
        cur=con.cursor()
        out=[]
        cn=set(_table_cols(cur,"CommandsNotes"))
        if {"note_name","category","sub_category","command","tags"}.issubset(cn):
            has_desc="description" in cn
            sel="id,note_name,category,sub_category,command,tags"+(",description" if has_desc else "")
            cur.execute(f"SELECT {sel} FROM CommandsNotes ORDER BY id DESC")
            for r in cur.fetchall():
                rid=r[0];nn=r[1];c=r[2];sc=r[3];cmd=r[4];tags=r[5];desc=(r[6] if has_desc else "")
                title=_norm(nn) or "Untitled"
                out.append({"id":int(rid),"src":"CommandsNotes","title":title,"category":_norm(c) or "Uncategorized","sub":_norm(sc) or "General","command":_clean_cmd(cmd),"tags":_norm(tags),"description":_norm(desc)})
        cc=set(_table_cols(cur,"Commands"))
        if {"note_name","category","sub_category","command","tags"}.issubset(cc):
            has_desc="description" in cc
            has_title="cmd_note_title" in cc
            sel="id,note_name,category,sub_category,command,tags"+(",description" if has_desc else "")+(",cmd_note_title" if has_title else "")
            cur.execute(f"SELECT {sel} FROM Commands ORDER BY id DESC")
            for r in cur.fetchall():
                rid=r[0];nn=r[1];c=r[2];sc=r[3];cmd=r[4];tags=r[5]
                off=6
                desc=(r[off] if has_desc else "");off+=1 if has_desc else 0
                ttl=(r[off] if has_title else "")
                base=_norm(nn) or "Untitled"
                title=_norm(ttl) or base
                out.append({"id":int(rid),"src":"Commands","title":title,"category":_norm(c) or "Uncategorized","sub":_norm(sc) or "General","command":_clean_cmd(cmd),"tags":_norm(tags),"description":_norm(desc)})
        con.close()
        _log("[+]",f"Loaded search cmds: {len(out)} from {os.path.basename(p)}")
        return p,out
    except Exception as e:
        _log("[!]",f"DB load error ({e})")
        try:con.close()
        except:pass
        return p,[]
def _targets_path():
    d=_abs("..","Data")
    p1=os.path.join(d,"Targets.json")
    p2=os.path.join(d,"Targes.json")
    if os.path.isfile(p1) or not os.path.isfile(p2):return p1
    return p2
def _read_json(p,default):
    try:
        if not p or not os.path.isfile(p):return default
        with open(p,"r",encoding="utf-8") as f:
            v=json.load(f)
            return v if v is not None else default
    except:return default
def _write_json(p,obj):
    t=p+".tmp"
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(t,"w",encoding="utf-8") as f:json.dump(obj,f,ensure_ascii=False,indent=2)
        os.replace(t,p);return True
    except:
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _searches_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"saved_searches.json")
def _load_searches():
    d=_read_json(_searches_path(),[])
    return d if isinstance(d,list) else []
def _save_searches(items):
    return _write_json(_searches_path(),items or [])
def _split_tags(s):
    if not s:return []
    raw=str(s).replace(";",",").split(",")
    out=[];seen=set()
    for p in raw:
        t=_norm(p)
        if not t:continue
        k=t.lower()
        if k in seen:continue
        seen.add(k);out.append(t)
    return out
class LiveTargetContext:
    def __init__(self):
        self.path=_targets_path()
        self.mtime=_safe_mtime(self.path)
        self.name=""
        self.map={}
        self.reload()
    def reload(self):
        self.path=_targets_path()
        self.mtime=_safe_mtime(self.path)
        data=_read_json(self.path,[])
        live=None
        if isinstance(data,list):
            for t in data:
                if not isinstance(t,dict):continue
                if _l(t.get("status",""))=="live":
                    live=t;break
        self.name=_norm(live.get("name","")) if live else ""
        vals=live.get("values",{}) if live else {}
        m={}
        if isinstance(vals,dict):
            for k,v in vals.items():
                kk=_l(k);vv=_norm(v)
                if kk and vv:m[kk]=vv
        self.map=m
    def changed(self):
        p=_targets_path()
        mt=_safe_mtime(p)
        return p!=self.path or mt!=self.mtime
class CommandReplacer:
    def __init__(self,ctx:LiveTargetContext):
        self.ctx=ctx
        self._rx=re.compile(r"\{([^{}]+)\}")
    def apply(self,cmd):
        s=_norm(cmd)
        if not s:return ""
        mp=getattr(self.ctx,"map",{}) or {}
        if not mp:return s
        def repl(m):
            k=_l(m.group(1))
            if k in mp:return mp[k]
            return "{"+m.group(1)+"}"
        try:return self._rx.sub(repl,s)
        except:return s
class Table_Style(QWidget):
    def __init__(self,on_copy,get_cmd,parent=None):
        super().__init__(parent)
        self._notes=[];self._view=[];self._q="";self._mode="Keyword";self._on_copy=on_copy;self._get_cmd=get_cmd
        self._src_filter="All";self._cat_filter="All";self._sub_filter="All";self._tag_filter="All"
        self._auto_cols=True;self._auto_limit=200
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.wrap=QFrame(self);self.wrap.setObjectName("HomeTableFrame");root.addWidget(self.wrap,1)
        v=QVBoxLayout(self.wrap);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        self.table=QTableWidget(self.wrap);self.table.setObjectName("HomeTable")
        self._c_title=0;self._c_cat=1;self._c_sub=2;self._c_tags=3;self._c_cmd=4;self._c_copy=5
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Title","Category","Sub","Tags","Command","⧉"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.cellClicked.connect(self._click)
        self.table.cellDoubleClicked.connect(self._dbl)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._ctx)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hf=h.font();hf.setBold(True);hf.setWeight(800);h.setFont(hf)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(self._c_title,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._c_cat,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._c_sub,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._c_tags,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._c_cmd,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self._c_copy,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self._c_copy,44)
        if hasattr(self.table,"setUniformRowHeights"):
            try:self.table.setUniformRowHeights(True)
            except Exception:pass
        self.table.verticalHeader().setDefaultSectionSize(44)
        v.addWidget(self.table,1)
    def set_notes(self,notes,apply=True):
        self._notes=list(notes or [])
        if apply:self._apply()
    def set_query(self,q,mode):
        self._q=_norm(q)
        self._mode=mode or "Keyword"
        self._apply()
    def set_filters(self,src,cat,sub,tag,apply=True):
        self._src_filter=src or "All"
        self._cat_filter=cat or "All"
        self._sub_filter=sub or "All"
        self._tag_filter=tag or "All"
        if apply:self._apply()
    def refresh_view(self):self._render()
    def _update_header_mode(self,row_count):
        auto=row_count<=self._auto_limit
        if auto==self._auto_cols:return
        self._auto_cols=auto
        h=self.table.horizontalHeader()
        if auto:
            h.setSectionResizeMode(self._c_title,QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(self._c_cat,QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(self._c_sub,QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(self._c_tags,QHeaderView.ResizeMode.ResizeToContents)
            return
        for c in (self._c_title,self._c_cat,self._c_sub,self._c_tags):
            h.setSectionResizeMode(c,QHeaderView.ResizeMode.Interactive)
        fm=QFontMetrics(self.table.font())
        self.table.setColumnWidth(self._c_title,max(180,fm.horizontalAdvance("Title")+140))
        self.table.setColumnWidth(self._c_cat,max(110,fm.horizontalAdvance("Category")+60))
        self.table.setColumnWidth(self._c_sub,max(110,fm.horizontalAdvance("Sub")+60))
        self.table.setColumnWidth(self._c_tags,max(130,fm.horizontalAdvance("Tags")+80))
    def _tok(self,s):
        s=_l(s)
        return [x for x in re.split(r"[,\s]+",s) if x]
    def _match(self,n,q,mode):
        src=_norm(self._src_filter)
        if src=="Linked" and _norm(n.get("src",""))!="Commands":return False
        if src=="Not Linked" and _norm(n.get("src",""))!="CommandsNotes":return False
        cat=_norm(self._cat_filter)
        if cat!="All" and _l(n.get("category",""))!=_l(cat):return False
        sub=_norm(self._sub_filter)
        if sub!="All" and _l(n.get("sub",""))!=_l(sub):return False
        tag=_norm(self._tag_filter)
        if tag!="All":
            tags=self._tok(n.get("tags",""))
            if _l(tag) not in [x.lower() for x in tags]:return False
        qq=_l(q)
        if not qq:return True
        if mode=="Category":return qq in _l(n.get("category",""))
        if mode=="Subcategory":return qq in _l(n.get("sub",""))
        if mode=="Tag":
            tags=_l(n.get("tags",""))
            if qq in tags:return True
            return qq in self._tok(tags)
        if mode=="Command":return qq in _l(n.get("command","")) or qq in _l(n.get("title",""))
        blob=" ".join([n.get("title",""),n.get("category",""),n.get("sub",""),n.get("tags",""),n.get("command",""),n.get("description","")])
        return qq in _l(blob)
    def _apply(self):
        q=self._q;mode=self._mode
        self._view=[n for n in self._notes if self._match(n,q,mode)]
        self._render()
    def _row_note(self,row):
        try:
            it=self.table.item(row,0)
            if not it:return None
            d=it.data(Qt.ItemDataRole.UserRole)
            return d if isinstance(d,dict) else None
        except:return None
    def _do_copy(self,n,raw=False):
        if not n:return
        cmd=n.get("command","") if raw else (self._get_cmd(n) if callable(self._get_cmd) else n.get("command",""))
        if callable(self._on_copy):self._on_copy(cmd,n.get("title",""))
    def _click(self,row,col):
        n=self._row_note(row)
        if n:self._do_copy(n,raw=False)
    def _dbl(self,row,col):
        n=self._row_note(row)
        if n:self._do_copy(n,raw=False)
    def _ctx(self,pos:QPoint):
        ix=self.table.indexAt(pos)
        if not ix.isValid():return
        n=self._row_note(ix.row())
        if not n:return
        m=QMenu(self)
        a1=QAction("Copy Command (Preview)",self);a1.triggered.connect(lambda:self._do_copy(n,raw=False))
        a2=QAction("Copy Raw Command",self);a2.triggered.connect(lambda:self._do_copy(n,raw=True))
        a3=QAction("Copy Title",self);a3.triggered.connect(lambda:(QApplication.clipboard().setText(n.get("title","") or ""),_log("[+]",f"Copied title: {n.get('title','')}")))
        a4=QAction("Copy Category/Sub",self);a4.triggered.connect(lambda:(QApplication.clipboard().setText(f"{n.get('category','')} > {n.get('sub','')}".strip()),_log("[+]",f"Copied path: {n.get('title','')}")))
        m.addAction(a1);m.addAction(a2);m.addSeparator();m.addAction(a3);m.addAction(a4)
        m.exec(self.table.viewport().mapToGlobal(pos))
    def _render(self):
        rows=self._view
        self._update_header_mode(len(rows))
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            for r,n in enumerate(rows):
                cmd_disp=self._get_cmd(n) if callable(self._get_cmd) else n.get("command","")
                vals=[_ell(n.get("title",""),120),_ell(n.get("category",""),40),_ell(n.get("sub",""),40),_ell(n.get("tags",""),60),_ell(cmd_disp,260),"⧉"]
                for c,val in enumerate(vals):
                    it=QTableWidgetItem(val if val is not None else "")
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                    if c==self._c_cmd:it.setToolTip(cmd_disp or "")
                    elif c==self._c_copy:it.setToolTip("Copy")
                    else:it.setToolTip(it.text())
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c in (self._c_cat,self._c_sub,self._c_tags,self._c_copy) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                    if c==0:it.setData(Qt.ItemDataRole.UserRole,n)
                    self.table.setItem(r,c,it)
            self.table.clearSelection()
        finally:
            self.table.setUpdatesEnabled(True)
class Split_View_Style(QWidget):
    def __init__(self,on_copy,get_cmd,parent=None):
        super().__init__(parent)
        self._notes=[];self._base=[];self._q="";self._mode="Keyword";self._on_copy=on_copy;self._get_cmd=get_cmd
        self._src_filter="All";self._cat_filter="All";self._sub_filter="All";self._tag_filter="All"
        self._auto_cols=True;self._auto_limit=200
        self._bar_cap=200
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.splitter=QSplitter(Qt.Orientation.Horizontal,self);self.splitter.setChildrenCollapsible(False);root.addWidget(self.splitter,1)
        self.cat_f=QFrame(self);self.cat_f.setObjectName("SplitCatsFrame")
        cv=QVBoxLayout(self.cat_f);cv.setContentsMargins(10,10,10,10);cv.setSpacing(8)
        self.ct=QLabel("Categories",self.cat_f);self.ct.setObjectName("SplitBarTitle")
        self.cat=QListWidget(self.cat_f);self.cat.setObjectName("SplitCatsList");self.cat.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.cat.setTextElideMode(Qt.TextElideMode.ElideRight);self.cat.itemSelectionChanged.connect(self._on_cat)
        cv.addWidget(self.ct,0);cv.addWidget(self.cat,1)
        self.sub_f=QFrame(self);self.sub_f.setObjectName("SplitSubsFrame")
        sv=QVBoxLayout(self.sub_f);sv.setContentsMargins(10,10,10,10);sv.setSpacing(8)
        self.st=QLabel("Subcategories",self.sub_f);self.st.setObjectName("SplitBarTitle")
        self.sub=QListWidget(self.sub_f);self.sub.setObjectName("SplitSubsList");self.sub.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.sub.setTextElideMode(Qt.TextElideMode.ElideRight);self.sub.itemSelectionChanged.connect(self._on_sub)
        sv.addWidget(self.st,0);sv.addWidget(self.sub,1)
        self.res_f=QFrame(self);self.res_f.setObjectName("HomeTableFrame")
        rv=QVBoxLayout(self.res_f);rv.setContentsMargins(10,10,10,10);rv.setSpacing(10)
        self.table=QTableWidget(self.res_f);self.table.setObjectName("HomeTable")
        self._c_title=0;self._c_tags=1;self._c_cmd=2;self._c_copy=3
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Title","Tags","Command","⧉"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.cellClicked.connect(self._click)
        self.table.cellDoubleClicked.connect(self._dbl)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._ctx)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hf=h.font();hf.setBold(True);hf.setWeight(800);h.setFont(hf)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(self._c_title,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._c_tags,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._c_cmd,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self._c_copy,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self._c_copy,44)
        if hasattr(self.table,"setUniformRowHeights"):
            try:self.table.setUniformRowHeights(True)
            except Exception:pass
        self.table.verticalHeader().setDefaultSectionSize(44)
        rv.addWidget(self.table,1)
        self.splitter.addWidget(self.cat_f);self.splitter.addWidget(self.sub_f);self.splitter.addWidget(self.res_f)
        self.splitter.setStretchFactor(0,0);self.splitter.setStretchFactor(1,0);self.splitter.setStretchFactor(2,1)
        QTimer.singleShot(0,self._fit_bars)
    def set_notes(self,notes,apply=True):
        self._notes=list(notes or [])
        if apply:self._apply()
    def set_query(self,q,mode):
        self._q=_norm(q)
        self._mode=mode or "Keyword"
        self._apply()
    def set_filters(self,src,cat,sub,tag,apply=True):
        self._src_filter=src or "All"
        self._cat_filter=cat or "All"
        self._sub_filter=sub or "All"
        self._tag_filter=tag or "All"
        if apply:self._apply()
    def refresh_view(self):self._render()
    def _update_header_mode(self,row_count):
        auto=row_count<=self._auto_limit
        if auto==self._auto_cols:return
        self._auto_cols=auto
        h=self.table.horizontalHeader()
        if auto:
            h.setSectionResizeMode(self._c_title,QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(self._c_tags,QHeaderView.ResizeMode.ResizeToContents)
            return
        for c in (self._c_title,self._c_tags):
            h.setSectionResizeMode(c,QHeaderView.ResizeMode.Interactive)
        fm=QFontMetrics(self.table.font())
        self.table.setColumnWidth(self._c_title,max(200,fm.horizontalAdvance("Title")+160))
        self.table.setColumnWidth(self._c_tags,max(140,fm.horizontalAdvance("Tags")+90))
    def _tok(self,s):
        s=_l(s)
        return [x for x in re.split(r"[,\s]+",s) if x]
    def _match(self,n,q,mode):
        src=_norm(self._src_filter)
        if src=="Linked" and _norm(n.get("src",""))!="Commands":return False
        if src=="Not Linked" and _norm(n.get("src",""))!="CommandsNotes":return False
        cat=_norm(self._cat_filter)
        if cat!="All" and _l(n.get("category",""))!=_l(cat):return False
        sub=_norm(self._sub_filter)
        if sub!="All" and _l(n.get("sub",""))!=_l(sub):return False
        tag=_norm(self._tag_filter)
        if tag!="All":
            tags=self._tok(n.get("tags",""))
            if _l(tag) not in [x.lower() for x in tags]:return False
        qq=_l(q)
        if not qq:return True
        if mode=="Category":return qq in _l(n.get("category",""))
        if mode=="Subcategory":return qq in _l(n.get("sub",""))
        if mode=="Tag":
            tags=_l(n.get("tags",""))
            if qq in tags:return True
            return qq in self._tok(tags)
        if mode=="Command":return qq in _l(n.get("command","")) or qq in _l(n.get("title",""))
        blob=" ".join([n.get("title",""),n.get("category",""),n.get("sub",""),n.get("tags",""),n.get("command",""),n.get("description","")])
        return qq in _l(blob)
    def _sel_text(self,w,default="All"):
        it=w.currentItem()
        return _norm(it.text()) if it else default
    def _set_list(self,w,items,keep):
        w.blockSignals(True)
        w.setUpdatesEnabled(False)
        try:
            w.clear()
            a=QListWidgetItem("All");a.setToolTip("All");w.addItem(a)
            for x in items:
                it=QListWidgetItem(x);it.setToolTip(x);w.addItem(it)
            sel=keep if keep in (["All"]+items) else "All"
            for i in range(w.count()):
                if _norm(w.item(i).text())==sel:w.setCurrentRow(i);break
        finally:
            w.setUpdatesEnabled(True)
            w.blockSignals(False)
    def _cats(self):
        d={}
        for n in self._base:
            c=_norm(n.get("category","")) or "Uncategorized"
            d[c]=1
        return sorted(d.keys(),key=lambda x:x.lower())
    def _subs(self,cat):
        d={}
        for n in self._base:
            c=_norm(n.get("category","")) or "Uncategorized"
            if cat!="All" and c!=cat:continue
            sc=_norm(n.get("sub","")) or "General"
            d[sc]=1
        return sorted(d.keys(),key=lambda x:x.lower())
    def _apply(self):
        q=self._q;mode=self._mode
        self._base=[n for n in self._notes if self._match(n,q,mode)]
        keep_cat=self._sel_text(self.cat)
        self._set_list(self.cat,self._cats(),keep_cat)
        cat=self._sel_text(self.cat)
        keep_sub=self._sel_text(self.sub)
        self._set_list(self.sub,self._subs(cat),keep_sub)
        self._fit_bars()
        self._render()
    def _filtered(self):
        cat=self._sel_text(self.cat);sub=self._sel_text(self.sub)
        out=[]
        for n in self._base:
            c=_norm(n.get("category","")) or "Uncategorized"
            sc=_norm(n.get("sub","")) or "General"
            if cat!="All" and c!=cat:continue
            if sub!="All" and sc!=sub:continue
            out.append(n)
        return out
    def _row_note(self,row):
        try:
            it=self.table.item(row,0)
            if not it:return None
            d=it.data(Qt.ItemDataRole.UserRole)
            return d if isinstance(d,dict) else None
        except:return None
    def _do_copy(self,n,raw=False):
        if not n:return
        cmd=n.get("command","") if raw else (self._get_cmd(n) if callable(self._get_cmd) else n.get("command",""))
        if callable(self._on_copy):self._on_copy(cmd,n.get("title",""))
    def _on_cat(self):
        cat=self._sel_text(self.cat)
        keep_sub=self._sel_text(self.sub)
        self._set_list(self.sub,self._subs(cat),keep_sub)
        self._fit_bars()
        self._render()
    def _on_sub(self):
        self._render()
    def _click(self,row,col):
        if col in (self._c_cmd,self._c_copy):
            n=self._row_note(row)
            if n:self._do_copy(n,raw=False)
    def _dbl(self,row,col):
        n=self._row_note(row)
        if n:self._do_copy(n,raw=False)
    def _ctx(self,pos:QPoint):
        ix=self.table.indexAt(pos)
        if not ix.isValid():return
        n=self._row_note(ix.row())
        if not n:return
        m=QMenu(self)
        a1=QAction("Copy Command (Preview)",self);a1.triggered.connect(lambda:self._do_copy(n,raw=False))
        a2=QAction("Copy Raw Command",self);a2.triggered.connect(lambda:self._do_copy(n,raw=True))
        a3=QAction("Copy Title",self);a3.triggered.connect(lambda:(QApplication.clipboard().setText(n.get("title","") or ""),_log("[+]",f"Copied title: {n.get('title','')}")))
        a4=QAction("Copy Category/Sub",self);a4.triggered.connect(lambda:(QApplication.clipboard().setText(f"{n.get('category','')} > {n.get('sub','')}".strip()),_log("[+]",f"Copied path: {n.get('title','')}")))
        m.addAction(a1);m.addAction(a2);m.addSeparator();m.addAction(a3);m.addAction(a4)
        m.exec(self.table.viewport().mapToGlobal(pos))
    def _render(self):
        rows=self._filtered()
        self._update_header_mode(len(rows))
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            for r,n in enumerate(rows):
                cmd_disp=self._get_cmd(n) if callable(self._get_cmd) else n.get("command","")
                vals=[_ell(n.get("title",""),120),_ell(n.get("tags",""),80),_ell(cmd_disp,260),"⧉"]
                for c,val in enumerate(vals):
                    it=QTableWidgetItem(val if val is not None else "")
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                    if c==self._c_cmd:it.setToolTip(cmd_disp or "")
                    elif c==self._c_copy:it.setToolTip("Copy")
                    else:it.setToolTip(it.text())
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c in (self._c_tags,self._c_copy) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                    if c==0:it.setData(Qt.ItemDataRole.UserRole,n)
                    self.table.setItem(r,c,it)
            self.table.clearSelection()
        finally:
            self.table.setUpdatesEnabled(True)
    def _fit_bars(self):
        def _w(lst,title):
            fm=QFontMetrics(lst.font());ft=QFontMetrics(title.font())
            mx=ft.horizontalAdvance(_norm(title.text()))
            for i in range(lst.count()):
                t=_norm(lst.item(i).text())
                if t:mx=max(mx,fm.horizontalAdvance(t))
            want=mx+fm.horizontalAdvance("MM")+30
            cap=self._bar_cap
            return min(want,cap),cap
        w1,cap1=_w(self.cat,self.ct);self.cat_f.setMinimumWidth(w1);self.cat_f.setMaximumWidth(cap1)
        w2,cap2=_w(self.sub,self.st);self.sub_f.setMinimumWidth(w2);self.sub_f.setMaximumWidth(cap2)
        sp=getattr(self,"splitter",None)
        if not sp:return
        def _fix():
            try:
                total=sp.size().width()
                if total<=50:
                    QTimer.singleShot(30,_fix);return
                h=sp.handleWidth() or 6
                left=self.cat_f.minimumWidth()
                mid=self.sub_f.minimumWidth()
                right=max(1,total-left-mid-(h*2)-30)
                sp.setSizes([left,mid,right])
                sp.updateGeometry()
                sp.repaint()
                for i in range(1,sp.count()):
                    try:
                        hh=sp.handle(i);hh.update();hh.repaint()
                    except:pass
            except:pass
        QTimer.singleShot(0,_fix)
        QTimer.singleShot(30,_fix)
class Widget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._db_path=None;self._db_mtime=None;self._notes=[];self._mode="Keyword";self._style="table"
        self._saved=_load_searches();self._applying_saved=False
        self._meta_cats=[];self._meta_subs={};self._meta_tags=[]
        self.ctx=LiveTargetContext()
        self.rep=CommandReplacer(self.ctx)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("HomeFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,0,14,0);top.setSpacing(10)
        self.btn_style=QToolButton(self.frame);self.btn_style.setObjectName("HomeAddBtn");self.btn_style.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_style.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_style.setStyleSheet("QToolButton{text-align:left;padding-right:18px} QToolButton::menu-indicator{image:none;width:0;height:0}")
        m=QMenu(self.btn_style)
        m.setStyleSheet("QMenu{background:#1e1e1e;border:1px solid #2b2b2b;border-radius:12px} QMenu::item{padding:8px 14px} QMenu::item:selected{background:#2b2b2b}")
        a1=QAction("Table",self);a1.triggered.connect(lambda:self._set_style("table",sync=False))
        a2=QAction("Split View",self);a2.triggered.connect(lambda:self._set_style("split",sync=False))
        m.addAction(a1);m.addAction(a2)
        self.btn_style.setMenu(m)
        self.search=QLineEdit(self.frame);self.search.setObjectName("HomeSearch");self.search.setPlaceholderText("Search...");self.search.textChanged.connect(self._on_search)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.search.setMinimumWidth(260)
        self.filter=QComboBox(self.frame);self.filter.setObjectName("HomePerPage");self.filter.addItems(["Keyword","Category","Subcategory","Tag","Command"]);self.filter.currentTextChanged.connect(self._on_filter)
        self.btn_clear=QToolButton(self.frame);self.btn_clear.setObjectName("HomeAddBtn");self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_clear.setText("Clear");self.btn_clear.clicked.connect(self._clear)
        self.btn_clear.setStyleSheet("QToolButton{text-align:center} QToolButton::menu-indicator{image:none;width:0;height:0}")
        self.btn_mini=QToolButton(self.frame);self.btn_mini.setObjectName("HomeAddBtn");self.btn_mini.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_mini.setText("Mini Mode");self.btn_mini.clicked.connect(self._open_mini)
        top.addWidget(self.btn_style,0);top.addWidget(self.search,1);top.addWidget(self.filter,0);top.addWidget(self.btn_clear,0);top.addWidget(self.btn_mini,0)
        v.addLayout(top,0)
        self.filt_box=QVBoxLayout();self.filt_box.setContentsMargins(14,0,14,0);self.filt_box.setSpacing(0)
        self.filt_row1=QHBoxLayout();self.filt_row1.setSpacing(10)
        self.filt_row2=QHBoxLayout();self.filt_row2.setSpacing(10)
        self.filt_box.addLayout(self.filt_row1);self.filt_box.addLayout(self.filt_row2)
        self.lbl_saved=QLabel("Saved",self.frame)
        self.cmb_saved=QComboBox(self.frame);self.cmb_saved.setObjectName("HomePerPage")
        self.btn_save=QToolButton(self.frame);self.btn_save.setObjectName("HomeAddBtn");self.btn_save.setText("Save")
        self.btn_del=QToolButton(self.frame);self.btn_del.setObjectName("HomeAddBtn");self.btn_del.setText("Delete")
        self.lbl_src=QLabel("Source",self.frame)
        self.cmb_src=QComboBox(self.frame);self.cmb_src.setObjectName("HomePerPage");self.cmb_src.addItems(["All","Linked","Not Linked"])
        self.lbl_cat=QLabel("Category",self.frame)
        self.cmb_cat=QComboBox(self.frame);self.cmb_cat.setObjectName("HomePerPage")
        self.lbl_sub=QLabel("Sub",self.frame)
        self.cmb_sub=QComboBox(self.frame);self.cmb_sub.setObjectName("HomePerPage")
        self.lbl_tag=QLabel("Tag",self.frame)
        self.cmb_tag=QComboBox(self.frame);self.cmb_tag.setObjectName("HomePerPage")
        self.btn_save.clicked.connect(self._save_search)
        self.btn_del.clicked.connect(self._delete_search)
        self.cmb_saved.currentIndexChanged.connect(self._on_saved_select)
        self.cmb_src.currentTextChanged.connect(self._on_filter_change)
        self.cmb_cat.currentTextChanged.connect(self._on_cat_filter)
        self.cmb_sub.currentTextChanged.connect(self._on_filter_change)
        self.cmb_tag.currentTextChanged.connect(self._on_filter_change)
        self._filters_compact=None
        self._filters_visible=False
        self._layout_filters(False)
        v.addLayout(self.filt_box,0)
        self.stack=QStackedWidget(self.frame);self.stack.setObjectName("Stack");self.stack.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding);v.addWidget(self.stack,1)
        self.table_style=Table_Style(self._copy,self._cmd_preview,self.stack)
        self.split_style=Split_View_Style(self._copy,self._cmd_preview,self.stack)
        self.stack.addWidget(self.table_style);self.stack.addWidget(self.split_style)
        self._fit_top();self._refresh_saved_combo()
        self._set_style("table",sync=False)
        QTimer.singleShot(0,self.reload)
        self.t=QTimer(self);self.t.setInterval(900);self.t.timeout.connect(self._tick);self.t.start()
        _log("[+]",f"SearchCore ready")
    def _clear_layout(self,lay):
        while lay.count():
            it=lay.takeAt(0)
            w=it.widget()
            if w:w.setParent(None)
    def _set_filters_visible(self,visible):
        for w in (self.lbl_saved,self.cmb_saved,self.btn_save,self.btn_del,
                  self.lbl_src,self.cmb_src,self.lbl_cat,self.cmb_cat,
                  self.lbl_sub,self.cmb_sub,self.lbl_tag,self.cmb_tag):
            w.setVisible(bool(visible))
    def _layout_filters(self,compact):
        if not getattr(self,"_filters_visible",True):
            self._clear_layout(self.filt_row1)
            self._clear_layout(self.filt_row2)
            self.filt_box.setSpacing(0)
            self._set_filters_visible(False)
            self._filters_compact=compact
            return
        if getattr(self,"_filters_compact",None)==compact:return
        self._filters_compact=compact
        self._clear_layout(self.filt_row1)
        self._clear_layout(self.filt_row2)
        self.filt_box.setSpacing(6 if compact else 0)
        if compact:
            self.filt_row1.addWidget(self.lbl_saved,0)
            self.filt_row1.addWidget(self.cmb_saved,1)
            self.filt_row1.addWidget(self.btn_save,0)
            self.filt_row1.addWidget(self.btn_del,0)
            self.filt_row1.addStretch(1)
            self.filt_row2.addWidget(self.lbl_src,0)
            self.filt_row2.addWidget(self.cmb_src,1)
            self.filt_row2.addWidget(self.lbl_cat,0)
            self.filt_row2.addWidget(self.cmb_cat,1)
            self.filt_row2.addWidget(self.lbl_sub,0)
            self.filt_row2.addWidget(self.cmb_sub,1)
            self.filt_row2.addWidget(self.lbl_tag,0)
            self.filt_row2.addWidget(self.cmb_tag,1)
            self.filt_row2.addStretch(1)
            return
        self.filt_row1.addWidget(self.lbl_saved,0)
        self.filt_row1.addWidget(self.cmb_saved,0)
        self.filt_row1.addWidget(self.btn_save,0)
        self.filt_row1.addWidget(self.btn_del,0)
        self.filt_row1.addSpacing(10)
        self.filt_row1.addWidget(self.lbl_src,0)
        self.filt_row1.addWidget(self.cmb_src,0)
        self.filt_row1.addWidget(self.lbl_cat,0)
        self.filt_row1.addWidget(self.cmb_cat,0)
        self.filt_row1.addWidget(self.lbl_sub,0)
        self.filt_row1.addWidget(self.cmb_sub,0)
        self.filt_row1.addWidget(self.lbl_tag,0)
        self.filt_row1.addWidget(self.cmb_tag,0)
        self.filt_row1.addStretch(1)
    def _fit_top(self):
        h=30
        for w in (self.btn_style,self.search,self.filter,self.btn_clear,self.btn_mini,self.cmb_saved,self.cmb_src,self.cmb_cat,self.cmb_sub,self.cmb_tag,self.btn_save,self.btn_del):w.setFixedHeight(h)
        for w in (self.lbl_saved,self.lbl_src,self.lbl_cat,self.lbl_sub,self.lbl_tag):w.setFixedHeight(h)
        width=self.frame.width() if self.frame.width()>0 else self.width()
        compact=width<1100
        fm_btn=QFontMetrics(self.btn_style.font())
        bw=max(fm_btn.horizontalAdvance(s+"  ▼") for s in ("Table","Split View"))+60
        if bw<180:bw=180
        self.btn_style.setFixedWidth(bw)
        fm_cmb=QFontMetrics(self.filter.font());self.filter.setFixedWidth(max(fm_cmb.horizontalAdvance(self.filter.itemText(i)) for i in range(self.filter.count()))+50)
        fm_clr=QFontMetrics(self.btn_clear.font());self.btn_clear.setFixedWidth(fm_clr.horizontalAdvance("Clear")+28)
        fm_mini=QFontMetrics(self.btn_mini.font());self.btn_mini.setFixedWidth(fm_mini.horizontalAdvance("Mini Mode")+28)
        for w in (self.cmb_saved,self.cmb_src,self.cmb_cat,self.cmb_sub,self.cmb_tag):
            w.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.search.setMinimumWidth(200 if compact else 260)
        self.cmb_saved.setMinimumWidth(120 if compact else 180)
        self.cmb_src.setMinimumWidth(90 if compact else 120)
        self.cmb_cat.setMinimumWidth(120 if compact else 150)
        self.cmb_sub.setMinimumWidth(120 if compact else 150)
        self.cmb_tag.setMinimumWidth(90 if compact else 120)
        fm_act=QFontMetrics(self.btn_save.font())
        pad=34 if compact else 40
        self.btn_save.setFixedWidth(fm_act.horizontalAdvance("Save")+pad)
        self.btn_del.setFixedWidth(fm_act.horizontalAdvance("Delete")+pad)
        self._layout_filters(compact)
    def resizeEvent(self,e):
        try:super().resizeEvent(e)
        except:pass
        try:self._fit_top()
        except:pass
    def _refresh_saved_combo(self,select_name=None):
        self.cmb_saved.blockSignals(True)
        self.cmb_saved.clear()
        self.cmb_saved.addItem("Saved searches")
        for s in (self._saved or []):
            name=_norm(s.get("name",""))
            if not name:continue
            self.cmb_saved.addItem(name)
            self.cmb_saved.setItemData(self.cmb_saved.count()-1,s)
        if select_name:
            sel=_l(select_name)
            for i in range(self.cmb_saved.count()):
                if _l(self.cmb_saved.itemText(i))==sel:
                    self.cmb_saved.setCurrentIndex(i)
                    break
        self.cmb_saved.blockSignals(False)
    def _clear_saved_selection(self):
        if self.cmb_saved.currentIndex()!=0:
            self.cmb_saved.blockSignals(True)
            self.cmb_saved.setCurrentIndex(0)
            self.cmb_saved.blockSignals(False)
    def _set_combo_value(self,combo,val):
        v=_norm(val) or "All"
        idx=combo.findText(v,Qt.MatchFlag.MatchFixedString)
        if idx<0:
            lv=_l(v)
            for i in range(combo.count()):
                if _l(combo.itemText(i))==lv:
                    idx=i;break
        combo.setCurrentIndex(idx if idx>=0 else 0)
    def _set_combo_items(self,combo,items,keep):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("All")
        for x in items or []:combo.addItem(x)
        self._set_combo_value(combo,keep)
        combo.blockSignals(False)
    def _collect_meta(self):
        cats=set();subs={};tags=set()
        for n in (self._notes or []):
            c=_norm(n.get("category","")) or "Uncategorized"
            sc=_norm(n.get("sub","")) or "General"
            cats.add(c);subs.setdefault(c,set()).add(sc)
            for t in _split_tags(n.get("tags","")):tags.add(t)
        self._meta_cats=sorted(list(cats),key=lambda x:x.lower())
        self._meta_subs={k:sorted(list(v),key=lambda x:x.lower()) for k,v in subs.items()}
        self._meta_tags=sorted(list(tags),key=lambda x:x.lower())
    def _refresh_sub_combo(self,keep):
        cat=_norm(self.cmb_cat.currentText()) or "All"
        if cat=="All":
            all_subs=set()
            for v in self._meta_subs.values():all_subs.update(v)
            items=sorted(list(all_subs),key=lambda x:x.lower())
        else:
            items=self._meta_subs.get(cat,[])
        self._set_combo_items(self.cmb_sub,items,keep)
    def _refresh_filter_options(self):
        keep_cat=_norm(self.cmb_cat.currentText())
        keep_sub=_norm(self.cmb_sub.currentText())
        keep_tag=_norm(self.cmb_tag.currentText())
        self._collect_meta()
        self._set_combo_items(self.cmb_cat,self._meta_cats,keep_cat)
        self._refresh_sub_combo(keep_sub)
        self._set_combo_items(self.cmb_tag,self._meta_tags,keep_tag)
        self._fit_top()
    def _current_filters(self):
        return {"src":self.cmb_src.currentText(),"category":self.cmb_cat.currentText(),"sub":self.cmb_sub.currentText(),"tag":self.cmb_tag.currentText()}
    def _current_search_entry(self,name):
        return {"name":_norm(name),"query":self.search.text(),"mode":self._mode,"filters":self._current_filters()}
    def _on_saved_select(self,idx):
        if idx<=0:return
        data=self.cmb_saved.itemData(idx)
        if not isinstance(data,dict):return
        self._applying_saved=True
        try:
            self.search.setText(data.get("query",""))
            self.filter.setCurrentText(data.get("mode","Keyword"))
            flt=data.get("filters",{}) if isinstance(data.get("filters",{}),dict) else {}
            self._set_combo_value(self.cmb_src,flt.get("src","All"))
            self._set_combo_value(self.cmb_cat,flt.get("category","All"))
            self._refresh_sub_combo(flt.get("sub","All"))
            self._set_combo_value(self.cmb_tag,flt.get("tag","All"))
        finally:
            self._applying_saved=False
        self._apply_query()
    def _save_search(self):
        name,ok=QInputDialog.getText(self,"Save Search","Name")
        if not ok:return
        name=_norm(name)
        if not name:return
        entry=self._current_search_entry(name)
        idx=None
        for i,s in enumerate(self._saved or []):
            if _l(s.get("name",""))==_l(name):idx=i;break
        if idx is not None:
            if QMessageBox.question(self,"Save Search",f"Overwrite saved search: {name}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            self._saved[idx]=entry
        else:
            self._saved.append(entry)
        _save_searches(self._saved)
        self._refresh_saved_combo(select_name=name)
    def _delete_search(self):
        idx=self.cmb_saved.currentIndex()
        if idx<=0:return
        name=self.cmb_saved.itemText(idx)
        if QMessageBox.question(self,"Delete Search",f"Delete saved search: {name}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self._saved=[s for s in (self._saved or []) if _l(s.get("name",""))!=_l(name)]
        _save_searches(self._saved)
        self._refresh_saved_combo()
    def _on_filter_change(self,*_):
        if not self._applying_saved:self._clear_saved_selection()
        self._apply_query()
    def _on_cat_filter(self,*_):
        keep=_norm(self.cmb_sub.currentText())
        self._refresh_sub_combo(keep)
        if not self._applying_saved:self._clear_saved_selection()
        self._apply_query()
    def _cmd_preview(self,n):
        if not n:return ""
        return self.rep.apply(n.get("command",""))
    def reload(self):
        self._db_path,self._notes=_load_cmds(self._db_path)
        self._db_mtime=_safe_mtime(self._db_path)
        self.table_style.set_notes(self._notes,apply=False)
        self.split_style.set_notes(self._notes,apply=False)
        self._refresh_filter_options()
        self._apply_query()
    def _tick(self):
        p=_db_path()
        mt=_safe_mtime(p)
        if p!=self._db_path or mt!=self._db_mtime:
            self.reload()
            return
        if self.ctx.changed():
            self.ctx.reload()
            if self._style=="split":
                self.split_style.refresh_view()
            else:
                self.table_style.refresh_view()
            return
    def _apply_query(self,style=None):
        q=self.search.text()
        flt=self._current_filters()
        use=(style or self._style) or "table"
        if use=="split":
            self.split_style.set_filters(flt.get("src"),flt.get("category"),flt.get("sub"),flt.get("tag"),apply=False)
            self.split_style.set_query(q,self._mode)
        else:
            self.table_style.set_filters(flt.get("src"),flt.get("category"),flt.get("sub"),flt.get("tag"),apply=False)
            self.table_style.set_query(q,self._mode)
    def _copy(self,cmd,title=""):
        try:
            QApplication.clipboard().setText(cmd or "")
            _log("[+]",f"Copied: {title}")
        except Exception as e:
            _log("[!]",f"Clipboard error ({e})")
    def _open_mini(self):
        try:
            w=self.window()
        except Exception:
            return
        if w and hasattr(w,"open_mini"):
            try:w.open_mini()
            except Exception:pass
    def _clear(self):
        self._applying_saved=True
        try:
            self.search.blockSignals(True);self.search.setText("");self.search.blockSignals(False)
            self.filter.setCurrentText("Keyword")
            self._set_combo_value(self.cmb_src,"All")
            self._set_combo_value(self.cmb_cat,"All")
            self._refresh_sub_combo("All")
            self._set_combo_value(self.cmb_tag,"All")
            self._clear_saved_selection()
        finally:
            self._applying_saved=False
        self._apply_query()
    def _on_search(self,t):
        if not self._applying_saved:self._clear_saved_selection()
        self._apply_query()
    def _on_filter(self,t):
        self._mode=t or "Keyword"
        if not self._applying_saved:self._clear_saved_selection()
        self._apply_query()
    def _set_style(self,style,sync=True):
        self._style="split" if style=="split" else "table"
        label="Split View" if self._style=="split" else "Table"
        try:self.btn_style.setText(f"{label}  ▼")
        except:pass
        self.stack.setCurrentIndex(1 if self._style=="split" else 0)
        if self._style=="split":
            QTimer.singleShot(0,self.split_style._fit_bars)
            QTimer.singleShot(30,self.split_style._fit_bars)
        _log("[*]",f"Style: {self._style}")
        if sync:self._apply_query()
