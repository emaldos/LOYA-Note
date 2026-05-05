import os,sqlite3,logging,importlib.util,re,html,hashlib,json,base64
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from PyQt6.QtCore import Qt,QSize,QTimer,pyqtSignal
from PyQt6.QtGui import QIcon,QAction,QFontMetrics,QColor
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QToolButton,QLineEdit,QTableWidget,QTableWidgetItem,QDialog,QFrame,QHeaderView,QComboBox,QLabel,QMessageBox,QSizePolicy,QMenu,QTextEdit,QPlainTextEdit
from Cores import common_db as _common_db
from Cores import note_refs as _note_refs
from Cores import recycle_bin as _recycle_bin
from Cores import CommandRelated as _command_related
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("CommandsNotes");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"CommandsNotes_log.log"))
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
    return _common_db.db_path()
DB_SCHEMA_VERSION=_common_db.DB_SCHEMA_VERSION
def _table_cols(cur,t):
    return _common_db.table_cols(cur,t)
def _ensure_schema(con):
    _common_db.ensure_schema(con)
def _apply_migrations(con):
    _common_db.apply_migrations(con)
def _norm(s):return (str(s) if s is not None else "").strip()
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
def _cmd_norm_data(d):
    d=d or {}
    title=d.get("cmd_note_title","") if "cmd_note_title" in d else (d.get("title","") or d.get("note_name",""))
    return {"cmd_note_title":_norm(title),"category":_norm(d.get("category","")),"sub_category":_norm(d.get("sub_category","") or d.get("sub","")),"description":_norm(d.get("description","")),"tags":_norm(d.get("tags","")),"command":(d.get("command","") or "").rstrip()}
def _cmd_id(d):
    x=_cmd_norm_data(d);raw="|".join([x.get("cmd_note_title",""),x.get("category",""),x.get("sub_category",""),x.get("description",""),x.get("tags",""),_norm(x.get("command",""))])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12] if raw else ""
def _encode_cmd_data(d):
    x=_cmd_norm_data(d);x["cid"]=_cmd_id(x)
    raw=json.dumps(x,ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
def _insert_cmdn_history(cur,cmd_id,note_name,category,subcat,cmd,tags,desc,action,action_at):
    try:
        cur.execute("INSERT INTO CommandsNotesHistory(cmd_id,note_name,category,sub_category,command,tags,description,action,action_at) VALUES(?,?,?,?,?,?,?,?,?)",(cmd_id,note_name,category,subcat,cmd,tags,desc,action,action_at))
    except:pass
def _insert_cmd_history(cur,cmd_id,note_id,note_name,cmd_note_title,category,subcat,desc,tags,cmd,action,action_at):
    try:
        cur.execute("INSERT INTO CommandsHistory(cmd_id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,action,action_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(cmd_id,note_id,note_name,cmd_note_title,category,subcat,desc,tags,cmd,action,action_at))
    except:pass
def _parse_cmd_meta(meta):
    d={"cmd_note_title":"","category":"","sub_category":"","description":"","tags":""}
    for p in [x.strip() for x in (meta or "").split(",") if x.strip()]:
        if ":" not in p:continue
        k,v=p.split(":",1)
        k=(k or "").strip().lower();v=(v or "").strip()
        if "command note tittle" in k or "note title" in k:d["cmd_note_title"]=v
        elif k=="category":d["category"]=v
        elif "sub category" in k or "subcategory" in k:d["sub_category"]=v
        elif k=="description":d["description"]=v
        elif k=="tags":d["tags"]=v
    return d
def _parse_cmd_blocks(text):
    t=text or ""
    out=[]
    for m in re.finditer(r"<C\s*\[(.*?)\]\s*>\s*(.*?)\s*</C>",t,re.S|re.I):
        meta=(m.group(1) or "").strip()
        body=_clean_cmd(m.group(2) or "")
        d={"cmd_note_title":"","category":"","sub_category":"","description":"","tags":"","command":body}
        d.update(_parse_cmd_meta(meta))
        if _norm(d.get("command")):out.append(d)
    return out
def _sync_missing_note_cmds(dbp):
    try:
        con=sqlite3.connect(dbp,timeout=5);_ensure_schema(con)
        cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Notes'")
        if not cur.fetchone():
            con.close();return 0
        cur.execute("SELECT id,note_name,content FROM Notes WHERE (content LIKE '%<C %' OR content LIKE '%&lt;C %') AND NOT EXISTS (SELECT 1 FROM Commands WHERE Commands.note_id=Notes.id)")
        rows=cur.fetchall()
        if not rows:
            con.close();return 0
        now=datetime.now(timezone.utc).isoformat()
        total=0
        for nid,name,content in rows:
            raw=html.unescape(content or "")
            cmds=_parse_cmd_blocks(raw)
            if not cmds:continue
            try:cur.execute("DELETE FROM Commands WHERE note_id=?",(int(nid),))
            except Exception:continue
            for c in cmds:
                try:
                    cur.execute("INSERT INTO Commands(note_id,note_name,cmd_note_title,category,sub_category,description,tags,command,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(int(nid),_norm(name),_norm(c.get("cmd_note_title","")),_norm(c.get("category","")),_norm(c.get("sub_category","")),_norm(c.get("description","")),_norm(c.get("tags","")),(c.get("command","") or "").rstrip(),now,now))
                    total+=1
                except Exception:
                    pass
        con.commit();con.close()
        _log("[+]",f"Synced commands from notes: {total}")
        return total
    except Exception as e:
        _log("[!]",f"Sync commands failed ({e})")
        try:con.close()
        except:pass
        return 0
def _load_cmds():
    p=_db_path()
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
                grp=_norm(r[2]) if "group_name" in notes_cols and len(r)>2 else ""
                try:note_groups_by_id[int(r[0])]=grp
                except Exception:pass
                nn=_norm(r[1])
                if nn:note_groups_by_name[nn.lower()]=grp
        cn=set(_table_cols(cur,"CommandsNotes"))
        if {"note_name","category","sub_category","command","tags"}.issubset(cn):
            has_desc="description" in cn
            sel="id,note_name,category,sub_category,command,tags"+(",description" if has_desc else "")
            cur.execute(f"SELECT {sel} FROM CommandsNotes ORDER BY id DESC")
            for r in cur.fetchall():
                rid=r[0];nn=r[1];c=r[2];sc=r[3];cmd=r[4];tags=r[5];desc=(r[6] if has_desc else "")
                out.append({"id":int(rid),"src":"CommandsNotes","locked":False,"note_id":None,"note_name":_norm(nn) or "Unlinked","cmd_note_title":_norm(nn) or "Unlinked","group_name":"","title":_norm(nn) or "Unlinked","category":_norm(c) or "Uncategorized","sub":_norm(sc) or "General","command":_clean_cmd(cmd),"tags":_norm(tags),"description":_norm(desc),"db":p})
        cc=set(_table_cols(cur,"Commands"))
        if {"note_name","category","sub_category","command","tags"}.issubset(cc):
            has_desc="description" in cc
            has_title="cmd_note_title" in cc
            has_note_id="note_id" in cc
            sel="id"+(",note_id" if has_note_id else "")+",note_name,category,sub_category,command,tags"+(",description" if has_desc else "")+(",cmd_note_title" if has_title else "")
            cur.execute(f"SELECT {sel} FROM Commands ORDER BY id DESC")
            for r in cur.fetchall():
                i=0
                rid=r[i];i+=1
                note_id=(r[i] if has_note_id else None);i+=1 if has_note_id else 0
                nn=r[i];i+=1
                c=r[i];i+=1
                sc=r[i];i+=1
                cmd=r[i];i+=1
                tags=r[i];i+=1
                desc=(r[i] if has_desc else "");i+=1 if has_desc else 0
                ttl=(r[i] if has_title else "")
                nn=_norm(nn) or "Unlinked"
                raw_ttl=_norm(ttl);ttl=raw_ttl or nn
                nid=(int(note_id) if str(note_id).isdigit() else None)
                grp=note_groups_by_id.get(nid,"") if nid is not None else note_groups_by_name.get(nn.lower(),"")
                out.append({"id":int(rid),"src":"Commands","locked":False,"note_id":nid,"note_name":nn,"cmd_note_title":raw_ttl,"group_name":grp,"title":ttl,"category":_norm(c) or "Uncategorized","sub":_norm(sc) or "General","command":_clean_cmd(cmd),"tags":_norm(tags),"description":_norm(desc),"db":p})
        con.close()
        _log("[+]",f"Loaded commands: {len(out)} from {os.path.basename(p)}")
        return p,out
    except Exception as e:
        _log("[!]",f"DB load error ({e})")
        try:con.close()
        except:pass
        return p,[]
def _delete_cmd(item):
    if not isinstance(item,dict):return False
    dbp=item.get("db");nid=item.get("id");src=item.get("src")
    if not dbp or nid is None:return False
    if src!="CommandsNotes":return False
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con)
            cur=con.cursor()
            cols=set(_table_cols(cur,"CommandsNotes"))
            key_col="id" if "id" in cols else "rowid"
            now=datetime.now(timezone.utc).isoformat()
            try:
                cur.execute(f"SELECT {key_col},note_name,category,sub_category,command,tags,description,created_at,updated_at FROM CommandsNotes WHERE {key_col}=?",(int(nid),))
                r=cur.fetchone()
                if r:
                    _insert_cmdn_history(cur,r[0],r[1],r[2],r[3],r[4],r[5],r[6],"delete",now)
                    _recycle_bin.put_entry_cur(cur,_recycle_bin.TYPE_COMMAND,_norm(r[1]) or "Unlinked",{"command":{"id":r[0],"note_name":r[1],"category":r[2],"sub_category":r[3],"command":r[4],"tags":r[5],"description":r[6],"created_at":r[7] if len(r)>7 else "","updated_at":r[8] if len(r)>8 else ""}},source="CommandsNotes",entity_key=str(r[0]),deleted_at=now,expires_at=_recycle_bin.expires_text())
            except:pass
            cur.execute(f"DELETE FROM CommandsNotes WHERE {key_col}=?",(int(nid),))
            con.commit()
            return bool(cur.rowcount)
    except Exception as e:
        _log("[!]",f"Delete error ({e})")
        return False
def _linked_command_rows(dbp,item):
    if not isinstance(item,dict):return []
    target=_cmd_id(item);out=[]
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con);cur=con.cursor();cols=set(_table_cols(cur,"Commands"))
            if not {"id","note_name","category","sub_category","command","tags"}.issubset(cols):return []
            has_desc="description" in cols;has_title="cmd_note_title" in cols;has_note_id="note_id" in cols
            sel="id"+(",note_id" if has_note_id else "")+",note_name,category,sub_category,command,tags"+(",description" if has_desc else "")+(",cmd_note_title" if has_title else "")
            cur.execute(f"SELECT {sel} FROM Commands")
            for r in cur.fetchall():
                i=0;rid=r[i];i+=1;nid=(r[i] if has_note_id else None);i+=1 if has_note_id else 0;nn=r[i];i+=1;cat=r[i];i+=1;sub=r[i];i+=1;cmd=r[i];i+=1;tags=r[i];i+=1;desc=(r[i] if has_desc else "");i+=1 if has_desc else 0;ttl=(r[i] if has_title else "")
                raw_ttl=_norm(ttl)
                row={"id":int(rid),"note_id":int(nid) if str(nid).isdigit() else None,"note_name":_norm(nn),"cmd_note_title":raw_ttl,"title":raw_ttl or _norm(nn),"category":_norm(cat),"sub":_norm(sub),"sub_category":_norm(sub),"description":_norm(desc),"tags":_norm(tags),"command":_clean_cmd(cmd)}
                if _cmd_id(row)==target:out.append(row)
    except Exception as e:_log("[!]",f"Linked command lookup failed ({e})")
    if not out and item.get("id") is not None:out=[item]
    return out
def _linked_note_count(dbp,item):
    rows=_linked_command_rows(dbp,item);seen=set()
    for r in rows:
        key=r.get("note_id") if r.get("note_id") is not None else _norm(r.get("note_name","")).lower()
        if key not in ("",None):seen.add(key)
    return len(seen) or (1 if item.get("src")=="Commands" else 0)
def _update_linked_command(dbp,old_item,new_item):
    if not dbp or not isinstance(old_item,dict) or not isinstance(new_item,dict):return False
    rows=_linked_command_rows(dbp,old_item);old_token=_encode_cmd_data(old_item);new_data=_cmd_norm_data(new_item);new_token=_encode_cmd_data(new_data);now=datetime.now(timezone.utc).isoformat()
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con);cur=con.cursor();cmd_cols=set(_table_cols(cur,"Commands"));note_cols=set(_table_cols(cur,"Notes"))
            ids=[int(r.get("id")) for r in rows if str(r.get("id")).isdigit()]
            if ids:
                q=",".join("?" for _ in ids)
                cur.execute(f"SELECT id,note_id,note_name,cmd_note_title,category,sub_category,description,tags,command FROM Commands WHERE id IN ({q})",ids)
                for r in cur.fetchall():_insert_cmd_history(cur,r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],"update",now)
                cur.execute(f"UPDATE Commands SET cmd_note_title=?,category=?,sub_category=?,description=?,tags=?,command=?,updated_at=? WHERE id IN ({q})",(new_data["cmd_note_title"],new_data["category"],new_data["sub_category"],new_data["description"],new_data["tags"],new_data["command"],now,*ids))
            note_ids=[];note_names=[]
            for r in rows:
                if r.get("note_id") is not None:note_ids.append(int(r.get("note_id")))
                elif _norm(r.get("note_name","")):note_names.append(_norm(r.get("note_name","")))
            notes=[]
            if "content" in note_cols:
                if note_ids:
                    q=",".join("?" for _ in sorted(set(note_ids)));cur.execute(f"SELECT id,note_name,content FROM Notes WHERE id IN ({q})",sorted(set(note_ids)));notes+=cur.fetchall()
                if note_names:
                    q=",".join("?" for _ in sorted(set(note_names)));cur.execute(f"SELECT id,note_name,content FROM Notes WHERE note_name IN ({q})",sorted(set(note_names)));notes+=cur.fetchall()
            seen=set()
            for nid,nn,content in notes:
                if nid in seen:continue
                seen.add(nid);htmls=content or "";new_html=htmls.replace(old_token,new_token)
                if new_html!=htmls:cur.execute("UPDATE Notes SET content=?,updated_at=? WHERE id=?",(new_html,now,int(nid)))
            con.commit()
            return True
    except Exception as e:
        _log("[!]",f"Linked command update failed ({e})")
        return False
class Widget(QWidget):
    command_saved=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self._dbp=None;self._cmds=[];self._view=[];self._page=1;self._per=10
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("CommandsNotesFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,0);top.setSpacing(10)
        self.btn_add=QToolButton(self.frame);self.btn_add.setObjectName("TargetAddBtn");self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.btn_add.setText("\u2003\u2003Add Command");self.btn_add.setIconSize(QSize(18,18))
        fa=self.btn_add.font();fa.setBold(True);fa.setWeight(800);self.btn_add.setFont(fa)
        self.btn_add.setMinimumHeight(30);self.btn_add.setMaximumHeight(30)
        ip1=_abs("..","Assets","add.png");ip2=_abs("..","Assets","Add.png")
        if os.path.isfile(ip1):self.btn_add.setIcon(QIcon(ip1))
        elif os.path.isfile(ip2):self.btn_add.setIcon(QIcon(ip2))
        else:_log("[-]",f"Add icon missing: {ip1}")
        self.btn_add.clicked.connect(self._on_add)
        self.search=QLineEdit(self.frame);self.search.setObjectName("TargetSearch");self.search.setPlaceholderText("Search commands...")
        self.search.setMinimumHeight(30);self.search.setMaximumHeight(30)
        self.search.textChanged.connect(self._on_search)
        self._link_filter="All"
        self.btn_filter=QToolButton(self.frame);self.btn_filter.setObjectName("HomeAddBtn");self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_filter.setStyleSheet("QToolButton{text-align:left;padding-right:18px} QToolButton::menu-indicator{image:none;width:0;height:0}")
        m=QMenu(self.btn_filter)
        m.setStyleSheet("QMenu{background:#1e1e1e;border:1px solid #2b2b2b;border-radius:12px} QMenu::item{padding:8px 14px} QMenu::item:selected{background:#2b2b2b}")
        a0=QAction("All",self);a0.triggered.connect(lambda:self._set_link_filter("All"))
        a1=QAction("Linked",self);a1.triggered.connect(lambda:self._set_link_filter("Linked"))
        a2=QAction("Not Linked",self);a2.triggered.connect(lambda:self._set_link_filter("Not Linked"))
        m.addAction(a0);m.addAction(a1);m.addAction(a2)
        self.btn_filter.setMenu(m)
        self.btn_filter.setFixedHeight(30)
        fm=QFontMetrics(self.btn_filter.font())
        bw=max(fm.horizontalAdvance(s+"  ▼") for s in ("All","Linked","Not Linked"))+40
        if bw<140:bw=140
        self.btn_filter.setFixedWidth(bw)
        self._set_link_filter("All",apply=False)
        top.addWidget(self.btn_add,0);top.addWidget(self.search,1);top.addWidget(self.btn_filter,0)
        self.tbl_wrap=QFrame(self.frame);self.tbl_wrap.setObjectName("TargetTableFrame")
        tw=QVBoxLayout(self.tbl_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.table=QTableWidget(self.tbl_wrap);self.table.setObjectName("TargetTable")
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["Note","Category","Sub","Tags","Command","Description","Inf","Edit","X"])
        self.table.setIconSize(QSize(20,20))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.cellClicked.connect(self._on_cell_click)
        self.table.cellDoubleClicked.connect(self._on_cell_double)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._ctx_menu)
        h=self.table.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        fh=h.font();fh.setBold(True);fh.setWeight(800);h.setFont(fh)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(6,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(7,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(8,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6,56);self.table.setColumnWidth(7,44);self.table.setColumnWidth(8,44)
        tw.addWidget(self.table,1)
        self.pager=QFrame(self.tbl_wrap);self.pager.setObjectName("CommandsPagerFrame")
        ph=QHBoxLayout(self.pager);ph.setContentsMargins(0,0,0,0);ph.setSpacing(10)
        self.pager_left=QWidget(self.pager);self.pager_left.setFixedWidth(150)
        left=QHBoxLayout(self.pager_left);left.setContentsMargins(0,0,0,0);left.setSpacing(0)
        self.lbl_total=QLabel("",self.pager_left);self.lbl_total.setObjectName("CommandsTotal")
        left.addWidget(self.lbl_total,0,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        mid=QHBoxLayout();mid.setContentsMargins(0,0,0,0);mid.setSpacing(8)
        self.btn_prev=QToolButton(self.pager);self.btn_prev.setObjectName("CommandsPagePrev");self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next=QToolButton(self.pager);self.btn_next.setObjectName("CommandsPageNext");self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        li=_abs("..","Assets","Left Arrow.png");ri=_abs("..","Assets","Right Arrow.png")
        if os.path.isfile(li):self.btn_prev.setIcon(QIcon(li));self.btn_prev.setIconSize(QSize(18,18));self.btn_prev.setText("")
        else:self.btn_prev.setText("<")
        if os.path.isfile(ri):self.btn_next.setIcon(QIcon(ri));self.btn_next.setIconSize(QSize(18,18));self.btn_next.setText("")
        else:self.btn_next.setText(">")
        self.lbl_page=QLabel("0 of 0",self.pager);self.lbl_page.setObjectName("CommandsPageLabel");self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter);self.lbl_page.setMinimumWidth(72)
        self.btn_prev.clicked.connect(self._prev_page);self.btn_next.clicked.connect(self._next_page)
        mid.addWidget(self.btn_prev,0,Qt.AlignmentFlag.AlignCenter);mid.addWidget(self.lbl_page,0,Qt.AlignmentFlag.AlignCenter);mid.addWidget(self.btn_next,0,Qt.AlignmentFlag.AlignCenter)
        self.pager_right=QWidget(self.pager);self.pager_right.setFixedWidth(150)
        right=QHBoxLayout(self.pager_right);right.setContentsMargins(0,0,0,0);right.setSpacing(8)
        self.cmb_per=QComboBox(self.pager_right);self.cmb_per.setObjectName("CommandsPerPage");self.cmb_per.setMinimumWidth(66);self.cmb_per.setMaximumWidth(66)
        self.cmb_per.addItems(["10","20","50","100"]);self.cmb_per.setCurrentText("10")
        self.cmb_per.currentTextChanged.connect(self._on_per_page)
        self.lbl_per=QLabel("per page",self.pager_right);self.lbl_per.setObjectName("CommandsPerPageLbl")
        right.addWidget(self.cmb_per,0);right.addWidget(self.lbl_per,0)
        ph.addWidget(self.pager_left,0);ph.addStretch(1);ph.addLayout(mid,0);ph.addStretch(1);ph.addWidget(self.pager_right,0)
        tw.addWidget(self.pager,0)
        v.addLayout(top);v.addWidget(self.tbl_wrap,1)
        QTimer.singleShot(0,self.reload)
        _log("[+]",f"CommandsNotes ready db={_db_path()}")
    def reload(self):
        try:_sync_missing_note_cmds(self._dbp or _db_path())
        except Exception:pass
        self._dbp,self._cmds=_load_cmds()
        self._page=1
        self._apply()
    def open_command_info(self,item):
        try:self._open_info(item)
        except Exception:pass
    def open_command_editor(self,item):
        try:self._open_add(item)
        except Exception:pass
    def _apply(self):
        q=_norm(self.search.text()).lower()
        f=_norm(getattr(self,"_link_filter","All"))
        base=self._cmds
        if f=="Linked":base=[x for x in base if x.get("src")=="Commands"]
        elif f=="Not Linked":base=[x for x in base if x.get("src")=="CommandsNotes"]
        if not q:self._view=list(base)
        else:
            out=[]
            for n in base:
                blob=" ".join([n.get("title",""),n.get("note_name",""),n.get("category",""),n.get("sub",""),n.get("tags",""),n.get("command",""),n.get("description","")]).lower()
                if q in blob:out.append(n)
            self._view=out
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
    def _linked_note_name(self,n):
        if not isinstance(n,dict):return ""
        dbp=n.get("db") or self._dbp
        fallback=_norm(n.get("note_name","")) or "Unlinked"
        ref=_note_refs.resolve_note_ref(dbp,note_id=n.get("note_id"),note_name=n.get("note_name",""))
        return (_note_refs.note_ref_name(ref) if ref else "") or fallback
    def _set_row(self,r,n):
        self._set_item(r,0,_ell(n.get("title","") or n.get("note_name",""),60),n.get("title","") or n.get("note_name",""),Qt.AlignmentFlag.AlignCenter,True)
        self._set_item(r,1,_ell(n.get("category",""),40),n.get("category",""),Qt.AlignmentFlag.AlignCenter)
        self._set_item(r,2,_ell(n.get("sub",""),40),n.get("sub",""),Qt.AlignmentFlag.AlignCenter)
        self._set_item(r,3,_ell(n.get("tags",""),60),n.get("tags",""),Qt.AlignmentFlag.AlignCenter)
        self._set_item(r,4,_ell(n.get("command",""),140),n.get("command",""),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
        self._set_item(r,5,_ell(n.get("description",""),140),n.get("description",""),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
        info=QTableWidgetItem("");info.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);info.setTextAlignment(Qt.AlignmentFlag.AlignCenter);info.setToolTip("Info")
        ip=_abs("..","Assets","info.png")
        if os.path.isfile(ip):info.setIcon(QIcon(ip))
        else:info.setText("Inf")
        self.table.setItem(r,6,info)
        ed=QTableWidgetItem("");ed.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);ed.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        ei=_abs("..","Assets","Edit.png")
        if os.path.isfile(ei):ed.setIcon(QIcon(ei))
        else:ed.setText("Edit")
        self.table.setItem(r,7,ed)
        self._set_item(r,8,"X",None,Qt.AlignmentFlag.AlignCenter,True)
        edit_it=self.table.item(r,7)
        if edit_it:
            edit_it.setToolTip("Edit linked command" if n.get("src")=="Commands" else "Edit")
        del_it=self.table.item(r,8)
        if del_it:
            if n.get("src")=="Commands":
                del_it.setToolTip("Linked command; delete from the original Note.")
                del_it.setForeground(QColor("#6f6f6f"))
            else:del_it.setToolTip("Delete")
        self.table.setRowHeight(r,44)
        self.table.item(r,0).setData(Qt.ItemDataRole.UserRole,n)
    def _row_item(self,row):
        it=self.table.item(row,0)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _copy_text(self,val):
        s=_norm(val)
        if not s:return
        try:
            QApplication.clipboard().setText(s)
            _log("[+]",f"Copied: {s[:40]}")
        except Exception as e:
            _log("[!]",f"Copy failed ({e})")
    def _nav_notes(self):
        try:w=self.window()
        except Exception:return None
        if w and hasattr(w,"on_nav"):
            try:w.on_nav("notes")
            except Exception:pass
        return getattr(w,"page_notes",None) if w else None
    def _open_related_note(self,n):
        if not isinstance(n,dict):return False
        return _command_related.open_related_notes(self,n,n.get("db") or self._dbp,self._nav_notes)
    def _ctx_menu(self,pos):
        ix=self.table.indexAt(pos)
        if not ix.isValid():return
        row=ix.row()
        self.table.selectRow(row)
        n=self._row_item(row)
        if not n:return
        menu=QMenu(self)
        open_note=QAction("Open Related Note",self)
        open_note.setEnabled(bool(_command_related.related_notes(n.get("db") or self._dbp,n)))
        open_note.triggered.connect(lambda:self._on_open_related_note(n))
        menu.addAction(open_note)
        copy_cmd=QAction("Copy Command",self)
        copy_cmd.setEnabled(bool(_norm(n.get("command",""))))
        copy_cmd.triggered.connect(lambda:self._copy_text(n.get("command","")))
        menu.addAction(copy_cmd)
        menu.exec(self.table.viewport().mapToGlobal(pos))
    def _on_open_related_note(self,n):
        res=self._open_related_note(n)
        if res is None or res:return
        QMessageBox.information(self,"Open Note","Related note not found.")
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
    def _set_link_filter(self,mode,apply=True):
        self._link_filter=mode or "All"
        try:self.btn_filter.setText(f"{self._link_filter}  ▼")
        except:pass
        if apply:
            self._page=1
            self._apply()
    def _info_text(self,n):
        if not isinstance(n,dict):return ""
        title=_norm(n.get("title") or n.get("note_name",""))
        note_name=_norm(n.get("note_name",""))
        group_name=_norm(n.get("group_name",""))
        cat=_norm(n.get("category",""))
        sub=_norm(n.get("sub",""))
        tags=_norm(n.get("tags",""))
        desc=_norm(n.get("description",""))
        src="Linked" if n.get("src")=="Commands" else "Not Linked"
        cmd=n.get("command","") or ""
        lines=[f"Note Title: {title}"]
        if group_name:lines.append(f"Group: {group_name}")
        if note_name and note_name!=title:lines.append(f"Note Name: {note_name}")
        lines.append(f"Category: {cat}")
        lines.append(f"Sub Category: {sub}")
        lines.append(f"Tags: {tags}")
        lines.append(f"Description: {desc}")
        lines.append(f"Source: {src}")
        lines.append("")
        lines.append("Command:")
        lines.append(cmd)
        return "\n".join(lines).rstrip()
    def _info_payload(self,n):
        if not isinstance(n,dict):return {}
        title=_norm(n.get("title") or n.get("note_name","") or "Command")
        cmd=n.get("command","") or ""
        src="Linked to Note" if n.get("src")=="Commands" else "Standalone"
        try:rel=_command_related.related_notes(n.get("db") or self._dbp,n)
        except Exception:rel=[]
        names=[]
        for r in rel[:3]:
            v=_norm(r.get("title") or r.get("note_name") or r.get("name",""))
            if v:names.append(v)
        if len(rel)>3:names.append(f"+{len(rel)-3} more")
        related=", ".join(names) if names else "-"
        lines=max(1,len(str(cmd).splitlines()))
        stats=f"{len(str(cmd))} chars | {lines} line" + ("" if lines==1 else "s")
        rows=[("Used In",f"{len(rel)} note" + ("" if len(rel)==1 else "s")),("Related Notes",related),("Group",n.get("group_name","")),("Category",n.get("category","")),("Sub Category",n.get("sub","")),("Tags",n.get("tags","")),("Description",n.get("description","")),("Command Size",stats)]
        return {"title":title,"cmd":cmd,"source":src,"related_count":len(rel),"rows":rows}
    def _info_chip(self,parent,text,obj="CommandInfoChip"):
        w=QLabel(text,parent);w.setObjectName(obj);w.setAlignment(Qt.AlignmentFlag.AlignCenter);w.setMinimumHeight(28);w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);return w
    def _info_row(self,parent,k,v):
        row=QFrame(parent);row.setObjectName("CommandInfoRow")
        h=QHBoxLayout(row);h.setContentsMargins(12,8,12,8);h.setSpacing(12)
        key=QLabel(k,row);key.setObjectName("CommandInfoKey");key.setFixedWidth(128);key.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        val=QLabel(_norm(v) or "-",row);val.setObjectName("CommandInfoValue");val.setWordWrap(True);val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        h.addWidget(key,0);h.addWidget(val,1)
        return row
    def _open_info(self,item):
        if not isinstance(item,dict):return
        data=self._info_payload(item)
        dlg=QDialog(self);dlg.setObjectName("TargetDialog")
        dlg.setWindowTitle("Command Info")
        g=QApplication.primaryScreen().availableGeometry()
        dlg.resize(min(780,int(g.width()*0.9)),min(620,int(g.height()*0.9)))
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):dlg.setWindowIcon(QIcon(ico))
        lay=QVBoxLayout(dlg);lay.setContentsMargins(14,14,14,14);lay.setSpacing(12)
        frame=QFrame(dlg);frame.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(frame);v.setContentsMargins(14,14,14,14);v.setSpacing(12)
        t=QLabel("Command Details",frame);t.setObjectName("TargetFormTitle")
        v.addWidget(t,0)
        hero=QFrame(frame);hero.setObjectName("CommandInfoHero")
        hv=QVBoxLayout(hero);hv.setContentsMargins(14,12,14,12);hv.setSpacing(8)
        top=QHBoxLayout();top.setContentsMargins(0,0,0,0);top.setSpacing(8)
        title=QLabel(data.get("title","Command"),hero);title.setObjectName("CommandInfoTitle");title.setWordWrap(True);title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(title,1);top.addWidget(self._info_chip(hero,data.get("source","Standalone")),0);top.addWidget(self._info_chip(hero,f"{data.get('related_count',0)} related","CommandInfoChipBlue"),0)
        sub=QLabel("Metadata, related note usage, and full command text",hero);sub.setObjectName("CommandInfoSub");sub.setWordWrap(True)
        hv.addLayout(top);hv.addWidget(sub,0)
        v.addWidget(hero,0)
        details=QFrame(frame);details.setObjectName("CommandInfoSection")
        dv=QVBoxLayout(details);dv.setContentsMargins(10,10,10,10);dv.setSpacing(6)
        dh=QLabel("Details",details);dh.setObjectName("CommandInfoSectionTitle");dv.addWidget(dh,0)
        rows=data.get("rows",[])
        for i in range(0,len(rows),2):
            pair=QHBoxLayout();pair.setContentsMargins(0,0,0,0);pair.setSpacing(8)
            k,val=rows[i];pair.addWidget(self._info_row(details,k,val),1)
            if i+1<len(rows):
                k,val=rows[i+1];pair.addWidget(self._info_row(details,k,val),1)
            else:pair.addStretch(1)
            dv.addLayout(pair,0)
        v.addWidget(details,0)
        cmd_box=QFrame(frame);cmd_box.setObjectName("CommandInfoSection")
        cv=QVBoxLayout(cmd_box);cv.setContentsMargins(10,10,10,10);cv.setSpacing(8)
        ch=QLabel("Command",cmd_box);ch.setObjectName("CommandInfoSectionTitle");cv.addWidget(ch,0)
        info=QPlainTextEdit(cmd_box);info.setObjectName("CommandInfoCommand");info.setReadOnly(True);info.setPlainText(data.get("cmd",""));info.setMinimumHeight(130)
        cv.addWidget(info,1)
        v.addWidget(cmd_box,1)
        bh=QHBoxLayout();bh.setContentsMargins(0,0,0,0);bh.setSpacing(10)
        cp=QToolButton(frame);cp.setObjectName("CmdSaveBtn");cp.setCursor(Qt.CursorShape.PointingHandCursor);cp.setText("Copy Command");cp.setMinimumHeight(30);cp.clicked.connect(lambda:self._copy_text(item.get("command","")))
        op=QToolButton(frame);op.setObjectName("CmdSaveBtn");op.setCursor(Qt.CursorShape.PointingHandCursor);op.setText("Open Related Note");op.setMinimumHeight(30);op.setEnabled(data.get("related_count",0)>0);op.clicked.connect(lambda:(dlg.accept(),self._on_open_related_note(item)))
        ok=QToolButton(frame);ok.setObjectName("TargetSaveBtn");ok.setCursor(Qt.CursorShape.PointingHandCursor);ok.setText("Close");ok.setMinimumHeight(30)
        ok.clicked.connect(dlg.accept)
        bh.addStretch(1);bh.addWidget(op,0);bh.addWidget(cp,0);bh.addWidget(ok,0);bh.addStretch(1)
        v.addLayout(bh,0)
        lay.addWidget(frame,1)
        dlg.exec()
    def _open_add(self,item=None):
        p=_abs("..","Cores","CommandsAdd.py")
        if not os.path.isfile(p):
            _log("[-]",f"CommandsAdd.py missing: {p}")
            return
        try:
            spec=importlib.util.spec_from_file_location("cmdadd_dyn",p)
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            cls=getattr(mod,"Widget",None)
            if cls is None:_log("[-]",f"CommandsAdd.Widget not found in: {p}");return
            dlg=QDialog(self);dlg.setObjectName("CommandsAddDialog")
            g=QApplication.primaryScreen().availableGeometry()
            dlg.resize(min(920,int(g.width()*0.9)),min(640,int(g.height()*0.9)))
            dlg.setWindowTitle("Edit Command" if item else "Add Command")
            ico=_abs("..","Assets","logox.png")
            if os.path.isfile(ico):dlg.setWindowIcon(QIcon(ico))
            lay=QVBoxLayout(dlg);lay.setContentsMargins(14,14,14,14);lay.setSpacing(12)
            w=cls()
            if item:
                try:w.set_item(item)
                except:pass
                if item.get("src")=="Commands":
                    cnt=len(_command_related.related_notes(item.get("db") or self._dbp,item)) or _linked_note_count(item.get("db") or self._dbp,item)
                    txt=f"This command is used in {cnt} note{'s' if cnt!=1 else ''}. If you update it here, it will be updated in all related notes."
                    try:w.set_warning_text(txt)
                    except Exception:pass
                    try:w.set_edit_target(item.get("db"),item.get("id"))
                    except Exception:pass
                    try:w.set_external_save(lambda data,old=dict(item):_update_linked_command(old.get("db") or self._dbp,old,data))
                    except Exception:pass
                else:
                    try:w.set_edit_target(item.get("db"),item.get("id"))
                    except:pass
            lay.addWidget(w,1)
            def _saved():
                try:self.reload()
                except:pass
                try:self.command_saved.emit()
                except:pass
                try:dlg.accept()
                except:pass
            try:w.command_saved.connect(_saved)
            except:
                try:w.note_saved.connect(_saved)
                except:_log("[-]","CommandsAdd has no saved signal")
            dlg.exec()
        except Exception as e:
            _log("[-]",f"Open CommandsAdd failed: {e}")
    def _on_add(self):
        _log("[*]","Add Command clicked")
        self._open_add(None)
    def _on_cell_click(self,row,col):
        n=self._row_item(row)
        if not n:return
        if col==6:
            self._open_info(n)
            return
        if col==7:
            _log("[*]",f"Edit clicked: {n.get('command','')[:40]}")
            self._open_add(n)
            return
        if col==8:
            if n.get("src")=="Commands":
                nn=self._linked_note_name(n)
                QMessageBox.information(self,"Linked",f"You can't delete this here.\n\nThis command belongs to Note:\n{nn}\n\nDelete it from the original Note, or delete the Note itself.")
                return
            w=self.window() if self.window() else self
            if QMessageBox.question(w,"Recycle Bin","Move this command to Recycle Bin?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            ok=_delete_cmd(n)
            if ok:_log("[+]",f"Moved command to Recycle Bin");self.reload()
            else:_log("[-]",f"Recycle Bin move failed");QMessageBox.critical(w,"Error","Failed to move command to Recycle Bin.")
    def _on_cell_double(self,row,col):
        n=self._row_item(row)
        if not n:return
        self._open_add(n)
