import os,sqlite3,logging,hashlib,json,re,html
from logging.handlers import RotatingFileHandler
from datetime import datetime,timezone
from PyQt6.QtCore import Qt,QTimer,QEvent,QStringListModel,pyqtSignal,QObject,QSize
from PyQt6.QtGui import QTextCursor,QIcon
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QTextEdit,QToolButton,QScrollArea,QMessageBox,QSizePolicy,QComboBox,QCompleter,QGridLayout,QListWidget,QListWidgetItem,QAbstractItemView,QDialog
from Cores import common_db as _common_db
def _abs(*p):return os.path.join(os.path.dirname(os.path.abspath(__file__)),*p)
def _log_setup():
    d=_abs("..","Logs");os.makedirs(d,exist_ok=True)
    lg=logging.getLogger("CommandsAdd");lg.setLevel(logging.INFO)
    fp=os.path.abspath(os.path.join(d,"CommandsAdd_log.log"))
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
def _norm_tag(t):return " ".join((t or "").strip().split())
def _cmd_text(s):return ("" if s is None else str(s))
def _split_tags(s):
    if not s:return []
    raw=str(s).replace(";",",").split(",")
    out=[];seen=set()
    for p in raw:
        t=_norm_tag(p)
        if not t:continue
        k=t.lower()
        if k in seen:continue
        seen.add(k);out.append(t)
    return out
def _targets_values_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"target_values.json")
def _targets_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    p=os.path.join(d,"Targets.json");old=os.path.join(d,"Targes.json")
    return p if os.path.isfile(p) or not os.path.isfile(old) else old
def _read_json(p,default=None):
    try:
        with open(p,"r",encoding="utf-8") as f:return json.load(f)
    except Exception:return default
def _clamp_u16(n):
    try:n=int(n)
    except:return 0
    if n<0:n=0
    if n>65535:n=65535
    return n
_SETTINGS_CACHE=None
_SETTINGS_MTIME=None
_KEY_RE_STRICT=re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_KEY_RE_EXT=re.compile(r"^[A-Za-z_][A-Za-z0-9_\-.:]*$")
def _settings_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"settings.json")
def _read_settings():
    global _SETTINGS_CACHE,_SETTINGS_MTIME
    p=_settings_path()
    try:m=os.path.getmtime(p)
    except:m=None
    if _SETTINGS_CACHE is not None and m==_SETTINGS_MTIME:return _SETTINGS_CACHE
    try:
        if not p or not os.path.isfile(p):
            _SETTINGS_CACHE={}
            _SETTINGS_MTIME=m
            return _SETTINGS_CACHE
        with open(p,"r",encoding="utf-8") as f:
            d=json.load(f)
            if not isinstance(d,dict):d={}
            _SETTINGS_CACHE=d
            _SETTINGS_MTIME=m
            return d
    except Exception:
        _SETTINGS_CACHE={}
        _SETTINGS_MTIME=m
        return _SETTINGS_CACHE
def _allow_dots_colons():
    s=_read_settings()
    t=s.get("targets",{}) if isinstance(s,dict) else {}
    return bool(t.get("allow_dots_colons",False))
def _is_valid_key(k):
    if not k:return False
    rx=_KEY_RE_EXT if _allow_dots_colons() else _KEY_RE_STRICT
    if not rx.match(k):return False
    return any(ch.isalpha() for ch in k)
def _load_target_priorities():
    p=_targets_values_path()
    exists=os.path.isfile(p)
    data=None
    if exists:
        try:
            with open(p,"r",encoding="utf-8") as f:data=json.load(f)
        except Exception:
            data=None
    out={}
    seen=set()
    dupe=False
    def addk(k,val,manual=False):
        nonlocal dupe
        nk=_norm_tag(k)
        if not nk:return
        if not _is_valid_key(nk):
            dupe=True
            return
        lk=nk.lower()
        if lk in seen:
            dupe=True
            return
        seen.add(lk);out[nk]={"priority":_clamp_u16(val),"manual":bool(manual)}
    if isinstance(data,dict):
        for k,v in data.items():
            if isinstance(v,dict):addk(k,v.get("priority",v.get("value",0)),v.get("manual",False))
            elif isinstance(v,int):addk(k,v,False)
            else:addk(k,0,False)
    elif isinstance(data,list):
        for it in data:
            if isinstance(it,str):addk(it,0)
            elif isinstance(it,dict):
                key=it.get("key") if "key" in it else it.get("name")
                addk(key,it.get("priority",it.get("value",0)),it.get("manual",False))
    if not out:out={}
    return out,exists,dupe
_TARGET_KEYS_CACHE=[]
_TARGET_KEYS_MTIME=None
def _get_target_key_list():
    global _TARGET_KEYS_CACHE,_TARGET_KEYS_MTIME
    p=_targets_values_path()
    try:mt=os.path.getmtime(p)
    except Exception:mt=None
    if _TARGET_KEYS_CACHE is not None and mt==_TARGET_KEYS_MTIME:
        return list(_TARGET_KEYS_CACHE or [])
    keys,_,_=_load_target_priorities()
    out=sorted(keys.keys(),key=lambda s:s.lower())
    _TARGET_KEYS_CACHE=out
    _TARGET_KEYS_MTIME=mt
    return list(out)
def _write_target_priorities(pri):
    p=_targets_values_path()
    t=p+".tmp"
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        data={}
        for k,v in (pri or {}).items():
            vv=_clamp_u16(v.get("priority",v.get("value",0)) if isinstance(v,dict) else v)
            entry={"priority":vv}
            if isinstance(v,dict) and v.get("manual"):entry["manual"]=True
            data[k]=entry
        with open(t,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(t,p)
        return True
    except Exception as e:
        _log("[!]",f"Target values write failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _extract_target_keys_from_db(dbp):
    keys=[]
    seen=set()
    if not dbp or not os.path.isfile(dbp):return keys
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5)
        cur=con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Commands'")
        if not cur.fetchone():return keys
        cols=set(_table_cols(cur,"Commands"))
        if "command" not in cols:return keys
        q="SELECT command FROM Commands WHERE command LIKE '%{{%' AND command LIKE '%}}%'"
        cur.execute(q)
        for (text,) in cur.fetchall():
            if not text:continue
            raw=html.unescape(str(text))
            for m in re.finditer(r"\{([^{}\r\n]+)\}",raw):
                k=_norm_tag(m.group(1))
                if not k or not _is_valid_key(k):continue
                lk=k.lower()
                if lk in seen:continue
                seen.add(lk);keys.append(k)
    except Exception:
        return keys
    finally:
        try:
            if con:con.close()
        except:pass
    return keys
def _target_keys_from_text(text):
    keys=[]
    if not text:return keys
    raw=html.unescape(str(text));seen=set()
    for m in re.finditer(r"\{([^{}\r\n]+)\}",raw):
        k=_norm_tag(m.group(1))
        if not k or not _is_valid_key(k):continue
        lk=k.lower()
        if lk in seen:continue
        seen.add(lk);keys.append(k)
    return keys
def _target_key_usage(dbp):
    out={}
    if not dbp or not os.path.isfile(dbp):return out
    con=None
    try:
        con=sqlite3.connect(dbp,timeout=5);cur=con.cursor()
        for table in ("Commands","CommandsNotes"):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",(table,))
            if not cur.fetchone():continue
            cols=set(_table_cols(cur,table))
            if "command" not in cols:continue
            cur.execute(f"SELECT command FROM {table} WHERE command LIKE '%{{%' AND command LIKE '%}}%'")
            for (text,) in cur.fetchall():
                for k in _target_keys_from_text(text):
                    lk=k.lower();row=out.get(lk,{"key":k,"count":0});row["count"]=int(row.get("count",0))+1;out[lk]=row
    except Exception:return out
    finally:
        try:
            if con:con.close()
        except:pass
    return out
_TARGET_ELEMENT_CACHE={}
def _safe_mtime(p):
    try:return os.path.getmtime(p) if p and os.path.isfile(p) else None
    except Exception:return None
def _clear_target_element_cache():
    try:_TARGET_ELEMENT_CACHE.clear()
    except Exception:pass
def _target_keys_from_targets():
    data=_read_json(_targets_path(),[])
    out=[];seen=set()
    if not isinstance(data,list):return out
    for t in data:
        vals=t.get("values",{}) if isinstance(t,dict) else {}
        if not isinstance(vals,dict):continue
        for k in vals.keys():
            nk=_norm_tag(k)
            if not nk or not _is_valid_key(nk):continue
            lk=nk.lower()
            if lk in seen:continue
            seen.add(lk);out.append(nk)
    return out
def _target_element_rows(dbp=None,prefix="",limit=0,force=False):
    dbp=dbp or _db_path()
    key=os.path.abspath(dbp),(_safe_mtime(dbp),_safe_mtime(_targets_values_path()),_safe_mtime(_targets_path()))
    if not force and key in _TARGET_ELEMENT_CACHE:base=list(_TARGET_ELEMENT_CACHE[key])
    else:
        pri,_,_=_load_target_priorities();usage=_target_key_usage(dbp);rows={}
        def add(k,priority=0,manual=False,source="target_values"):
            nk=_norm_tag(k)
            if not nk or not _is_valid_key(nk):return
            lk=nk.lower();cur=rows.get(lk,{})
            rows[lk]={"key":cur.get("key",nk),"token":"{"+cur.get("key",nk)+"}","priority":max(_clamp_u16(priority),int(cur.get("priority",0) or 0)),"manual":bool(cur.get("manual",False) or manual),"usage":int((usage.get(lk,{}) or {}).get("count",cur.get("usage",0)) or 0),"source":cur.get("source",source)}
        for k,v in (pri or {}).items():
            val=v.get("priority",v.get("value",0)) if isinstance(v,dict) else v
            add(k,val,bool(v.get("manual",False)) if isinstance(v,dict) else False,"target_values")
        for k in _target_keys_from_targets():add(k,0,False,"targets")
        for v in usage.values():add(v.get("key",""),0,False,"commands")
        base=list(rows.values());base.sort(key=lambda r:(-int(r.get("usage",0) or 0),r.get("key","").lower()));_TARGET_ELEMENT_CACHE[key]=list(base)
    pre=_norm_tag(prefix).lower()
    if pre:base=[r for r in base if r.get("key","").lower().startswith(pre)]
    try:lim=int(limit)
    except Exception:lim=0
    return base[:lim] if lim>0 else base
def _auto_add_target_values(dbp):
    keys=_extract_target_keys_from_db(dbp)
    if not keys:return 0
    pri,_,dupe=_load_target_priorities()
    existing={k.lower() for k in pri.keys()}
    added=0
    for k in keys:
        lk=k.lower()
        if lk in existing:continue
        pri[k]={"priority":0,"manual":False}
        existing.add(lk)
        added+=1
    if added>0 or dupe:
        _write_target_priorities(pri);_clear_target_element_cache()
    return added
class _PlaceholderCompleter(QObject):
    def __init__(self,edit,key_list_fn):
        super().__init__(edit)
        self._edit=edit
        self._key_list_fn=key_list_fn
        self._popup=QListWidget(edit)
        self._popup.setObjectName("PlaceholderSuggest")
        self._popup.setWindowFlags(Qt.WindowType.Popup)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._popup.itemClicked.connect(lambda it:self._apply_item(it.text()))
        self._popup.hide()
        edit.installEventFilter(self)
    def _sync_items(self):
        keys=[]
        try:keys=list(self._key_list_fn() or [])
        except Exception:keys=[]
        keys=[_norm_tag(k) for k in keys if _norm_tag(k)]
        seen=set();out=[]
        for k in keys:
            lk=k.lower()
            if lk in seen:continue
            seen.add(lk);out.append(k)
        return sorted(out,key=lambda s:s.lower())
    def _brace_context(self):
        cur=self._edit.textCursor()
        pos=cur.position()
        text=self._edit.toPlainText()
        if pos<0 or pos>len(text):return None
        left=text[:pos]
        last_open=left.rfind("{")
        if last_open<0:return None
        last_close=left.rfind("}")
        if last_close>last_open:return None
        prefix=left[last_open+1:]
        if not re.match(r"^[A-Za-z0-9_.:-]*$",prefix):return None
        return prefix,last_open+1
    def _show(self):
        ctx=self._brace_context()
        if not ctx:
            self._popup.hide()
            return
        prefix,_=ctx
        items=self._sync_items()
        if prefix:
            lp=prefix.lower()
            items=[k for k in items if k.lower().startswith(lp)]
        if not items:
            self._popup.hide()
            return
        self._popup.clear()
        self._popup.addItems(items)
        self._popup.setCurrentRow(0)
        row_h=self._popup.sizeHintForRow(0) or 20
        rows=min(6,len(items))
        height=rows*row_h+6
        width=max(200,self._popup.sizeHintForColumn(0)+24)
        self._popup.setFixedSize(width,height)
        rect=self._edit.cursorRect()
        pos=self._edit.mapToGlobal(rect.bottomLeft())
        self._popup.move(pos)
        self._popup.show()
    def _apply_item(self,txt):
        if not txt:return
        ctx=self._brace_context()
        if not ctx:return
        prefix,start=ctx
        cur=self._edit.textCursor()
        pos=cur.position()
        cur.beginEditBlock()
        cur.setPosition(start)
        cur.setPosition(pos,QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(txt)
        new_pos=cur.position()
        doc=self._edit.document()
        try:next_ch=str(doc.characterAt(new_pos))
        except Exception:next_ch=""
        if next_ch!="}":
            cur.insertText("}")
        else:
            try:cur.setPosition(new_pos+1)
            except Exception:pass
        cur.endEditBlock()
        self._edit.setTextCursor(cur)
        self._popup.hide()
    def eventFilter(self,obj,event):
        try:
            if obj is self._edit and event.type()==QEvent.Type.KeyPress:
                key=event.key()
                mods=event.modifiers()
                if self._popup.isVisible():
                    if key in (Qt.Key.Key_Up,Qt.Key.Key_Down):
                        row=self._popup.currentRow()
                        row+=-1 if key==Qt.Key.Key_Up else 1
                        row=max(0,min(self._popup.count()-1,row))
                        self._popup.setCurrentRow(row)
                        return True
                    if key in (Qt.Key.Key_Enter,Qt.Key.Key_Return,Qt.Key.Key_Tab):
                        it=self._popup.currentItem()
                        if it:self._apply_item(it.text())
                        return True
                    if key==Qt.Key.Key_Escape:
                        self._popup.hide()
                        return True
                if key==Qt.Key.Key_Space and (mods&Qt.KeyboardModifier.ControlModifier):
                    QTimer.singleShot(0,self._show)
                    return True
                if event.text()=="}":
                    self._popup.hide()
            if obj is self._edit and event.type() in (QEvent.Type.FocusOut,QEvent.Type.Hide):
                self._popup.hide()
        except Exception:
            return False
        return super().eventFilter(obj,event)
class _CmdElementSuggest(QObject):
    def __init__(self,edit,row_fn):
        super().__init__(edit);self._edit=edit;self._row_fn=row_fn
        self._popup=QListWidget(edit);self._popup.setObjectName("CmdElementSuggest");self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus);self._popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self._popup.itemClicked.connect(lambda it:self._apply_item(it));self._popup.hide()
        edit.installEventFilter(self);edit.textChanged.connect(lambda:QTimer.singleShot(0,self.refresh));edit.cursorPositionChanged.connect(lambda:QTimer.singleShot(0,self.refresh))
    def hide(self):self._popup.hide()
    def _brace_context(self):
        cur=self._edit.textCursor();pos=cur.position();text=self._edit.toPlainText()
        if pos<0 or pos>len(text):return None
        left=text[:pos];last_open=left.rfind("{")
        if last_open<0:return None
        if left.rfind("}")>last_open:return None
        prefix=left[last_open+1:]
        if not re.match(r"^[A-Za-z0-9_.:-]*$",prefix):return None
        return prefix,last_open+1,pos
    def _rows(self,prefix):
        try:return list(self._row_fn(prefix,3) or [])
        except Exception:return []
    def refresh(self):
        if not self._edit.isVisible() or not self._edit.hasFocus():self.hide();return
        ctx=self._brace_context()
        if not ctx:self.hide();return
        rows=self._rows(ctx[0])
        if not rows:self.hide();return
        self._popup.clear()
        for r in rows[:3]:
            token=r.get("token","") or ("{"+r.get("key","")+"}");it=QListWidgetItem(token);it.setData(Qt.ItemDataRole.UserRole,r);it.setToolTip(f"Usage: {int(r.get('usage',0) or 0)} | Priority: {int(r.get('priority',0) or 0)}");self._popup.addItem(it)
        self._popup.setCurrentRow(0)
        row_h=self._popup.sizeHintForRow(0) or 26
        self._popup.setFixedSize(max(180,self._popup.sizeHintForColumn(0)+34),min(3,self._popup.count())*row_h+8)
        root=self._edit.window() or self._edit
        if self._popup.parentWidget() is not root:self._popup.setParent(root)
        pos=root.mapFromGlobal(self._edit.viewport().mapToGlobal(self._edit.cursorRect().bottomLeft()))
        try:self._popup.move(max(0,min(pos.x(),root.width()-self._popup.width())),max(0,min(pos.y(),root.height()-self._popup.height())))
        except Exception:self._popup.move(pos)
        self._popup.show();self._popup.raise_()
    def _apply_item(self,it):
        if not it:return
        ctx=self._brace_context()
        if not ctx:return
        d=it.data(Qt.ItemDataRole.UserRole);token=(d.get("token","") if isinstance(d,dict) else "") or it.text();key=token.strip("{}")
        if not key:return
        _,start,pos=ctx;cur=self._edit.textCursor();cur.beginEditBlock();cur.setPosition(start);cur.setPosition(pos,QTextCursor.MoveMode.KeepAnchor);cur.removeSelectedText();cur.insertText(key);new_pos=cur.position()
        try:next_ch=str(self._edit.document().characterAt(new_pos))
        except Exception:next_ch=""
        if next_ch!="}":cur.insertText("}")
        else:cur.setPosition(new_pos+1)
        cur.endEditBlock();self._edit.setTextCursor(cur);self.hide()
    def eventFilter(self,obj,event):
        try:
            if obj is self._edit and event.type()==QEvent.Type.KeyPress:
                key=event.key()
                if self._popup.isVisible():
                    if key in (Qt.Key.Key_Up,Qt.Key.Key_Down):
                        row=self._popup.currentRow()+(-1 if key==Qt.Key.Key_Up else 1);self._popup.setCurrentRow(max(0,min(self._popup.count()-1,row)));return True
                    if key in (Qt.Key.Key_Enter,Qt.Key.Key_Return,Qt.Key.Key_Tab):self._apply_item(self._popup.currentItem());return True
                    if key==Qt.Key.Key_Escape:self.hide();return True
                if event.text()=="}":self.hide()
            if obj is self._edit and event.type() in (QEvent.Type.FocusOut,QEvent.Type.Hide):self.hide()
        except Exception:return False
        return super().eventFilter(obj,event)
class _TargetElementPickerDlg(QDialog):
    def __init__(self,parent,dbp):
        super().__init__(parent);self.setObjectName("CmdElementDialog");self.setWindowTitle("Existing Elements");self.resize(460,420);self._rows=_target_element_rows(dbp);self._selected=None
        root=QVBoxLayout(self);root.setContentsMargins(14,14,14,14);root.setSpacing(10)
        box=QFrame(self);box.setObjectName("TargetDialogFrame");v=QVBoxLayout(box);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        t=QLabel("Existing Elements",box);t.setObjectName("TargetFormTitle")
        self.search=QLineEdit(box);self.search.setObjectName("CmdElementSearch");self.search.setPlaceholderText("Search elements...")
        self.list=QListWidget(box);self.list.setObjectName("CmdElementList");self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.search.textChanged.connect(self._render);self.list.itemDoubleClicked.connect(lambda it:self._accept_item(it))
        v.addWidget(t,0);v.addWidget(self.search,0);v.addWidget(self.list,1)
        b=QHBoxLayout();b.setContentsMargins(0,0,0,0);b.setSpacing(8)
        self.btn_ok=QToolButton(box);self.btn_ok.setObjectName("CmdSaveBtn");self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ok.setText("Insert")
        self.btn_ca=QToolButton(box);self.btn_ca.setObjectName("CmdCancelBtn");self.btn_ca.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ca.setText("Cancel")
        self.btn_ok.clicked.connect(self._accept_selected);self.btn_ca.clicked.connect(self.reject)
        b.addStretch(1);b.addWidget(self.btn_ok,0);b.addWidget(self.btn_ca,0);v.addLayout(b);root.addWidget(box,1);self._render()
    def _render(self):
        q=_norm_tag(self.search.text()).strip("{}").lower();rows=list(self._rows or [])
        if q:rows=[r for r in rows if q in (r.get("key","")+" "+r.get("token","")+" "+r.get("source","")).lower()]
        self.list.clear()
        for r in rows:
            txt=r.get("token","") or ("{"+r.get("key","")+"}");it=QListWidgetItem(txt);it.setData(Qt.ItemDataRole.UserRole,r);it.setToolTip(f"Usage: {int(r.get('usage',0) or 0)} | Priority: {int(r.get('priority',0) or 0)} | Source: {r.get('source','')}");self.list.addItem(it)
        if self.list.count()>0:self.list.setCurrentRow(0)
        self.btn_ok.setEnabled(self.list.count()>0)
    def _accept_item(self,it):
        if not it:return
        d=it.data(Qt.ItemDataRole.UserRole);self._selected=d if isinstance(d,dict) else {};self.accept()
    def _accept_selected(self):self._accept_item(self.list.currentItem())
    def selected(self):return self._selected or {}
def _db_path():
    return _common_db.db_path()
DB_SCHEMA_VERSION=_common_db.DB_SCHEMA_VERSION
def _ensure_schema(con):
    _common_db.ensure_schema(con)
def _apply_migrations(con):
    _common_db.apply_migrations(con)
def _table_cols(cur,t):
    return _common_db.table_cols(cur,t)
def _insert_cmdn_history(cur,cmd_id,note_name,category,subcat,cmd,tags,desc,action,action_at):
    try:
        cur.execute("INSERT INTO CommandsNotesHistory(cmd_id,note_name,category,sub_category,command,tags,description,action,action_at) VALUES(?,?,?,?,?,?,?,?,?)",(cmd_id,note_name,category,subcat,cmd,tags,desc,action,action_at))
    except:pass
def _insert_cmd(dbp,note_name,category,subcat,cmd,tags,desc):
    with sqlite3.connect(dbp,timeout=5) as con:
        _ensure_schema(con)
        now=datetime.now(timezone.utc).isoformat()
        cur=con.cursor()
        cur.execute("INSERT INTO CommandsNotes(note_name,category,sub_category,command,tags,description,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(note_name,category,subcat,cmd,tags,desc,now,now))
        try:cid=int(cur.lastrowid)
        except:cid=None
        _insert_cmdn_history(cur,cid,note_name,category,subcat,cmd,tags,desc,"insert",now)
        con.commit()
        try:return int(cur.lastrowid)
        except:return None
def _update_cmd(dbp,nid,note_name,category,subcat,cmd,tags,desc):
    if nid is None:return False
    with sqlite3.connect(dbp,timeout=5) as con:
        _ensure_schema(con)
        now=datetime.now(timezone.utc).isoformat()
        cur=con.cursor()
        cols=_table_cols(cur,"CommandsNotes")
        key_col="id" if "id" in cols else "rowid"
        cur.execute(f"UPDATE CommandsNotes SET note_name=?,category=?,sub_category=?,command=?,tags=?,description=?,updated_at=? WHERE {key_col}=?",(note_name,category,subcat,cmd,tags,desc,now,int(nid)))
        if cur.rowcount:
            try:
                cur.execute(f"SELECT note_name,category,sub_category,command,tags,description FROM CommandsNotes WHERE {key_col}=?",(int(nid),))
                r=cur.fetchone()
                if r:_insert_cmdn_history(cur,int(nid),r[0],r[1],r[2],r[3],r[4],r[5],"update",now)
            except:pass
        con.commit()
        return bool(cur.rowcount)
def _history_from_db(dbp):
    out={"notes":[],"categories":[],"subcategories":[],"tags":[],"suggest_tags":[],"last_note":"","last_category":"","last_subcategory":""}
    if not dbp or not os.path.isfile(dbp):return out
    try:
        with sqlite3.connect(dbp,timeout=5) as con:
            _ensure_schema(con)
            cur=con.cursor()
            cur.execute("SELECT note_name,category,sub_category FROM CommandsNotes ORDER BY id DESC LIMIT 1")
            r=cur.fetchone()
            if r:
                out["last_note"]=_norm_tag(r[0])
                out["last_category"]=_norm_tag(r[1])
                out["last_subcategory"]=_norm_tag(r[2])
            cur.execute("SELECT DISTINCT note_name FROM CommandsNotes WHERE note_name IS NOT NULL AND TRIM(note_name)<>''")
            seen=set();notes=[]
            for (n,) in cur.fetchall():
                t=_norm_tag(n)
                if not t:continue
                k=t.lower()
                if k in seen:continue
                seen.add(k);notes.append(t)
            out["notes"]=notes
            cur.execute("SELECT DISTINCT category FROM CommandsNotes WHERE category IS NOT NULL AND TRIM(category)<>''")
            seen=set();cats=[]
            for (c,) in cur.fetchall():
                t=_norm_tag(c)
                if not t:continue
                k=t.lower()
                if k in seen:continue
                seen.add(k);cats.append(t)
            out["categories"]=cats
            cur.execute("SELECT DISTINCT sub_category FROM CommandsNotes WHERE sub_category IS NOT NULL AND TRIM(sub_category)<>''")
            seen=set();subs=[]
            for (s,) in cur.fetchall():
                t=_norm_tag(s)
                if not t:continue
                k=t.lower()
                if k in seen:continue
                seen.add(k);subs.append(t)
            out["subcategories"]=subs
            cur.execute("SELECT tags FROM CommandsNotes WHERE tags IS NOT NULL AND TRIM(tags)<>'' ORDER BY id ASC")
            all_tags=[];seen=set()
            for (t,) in cur.fetchall():
                for x in _split_tags(t):
                    k=x.lower()
                    if k in seen:continue
                    seen.add(k);all_tags.append(x)
            out["tags"]=all_tags
            cur.execute("SELECT tags FROM CommandsNotes WHERE tags IS NOT NULL AND TRIM(tags)<>'' ORDER BY id DESC LIMIT 200")
            sug=[];seen=set()
            for (t,) in cur.fetchall():
                for x in _split_tags(t):
                    k=x.lower()
                    if k in seen:continue
                    seen.add(k);sug.append(x)
                    if len(sug)>=5:break
                if len(sug)>=5:break
            out["suggest_tags"]=sug
    except:pass
    return out
def _x_btn_style():return "QToolButton{padding:0;margin:0;border:1px solid #2b2b2b;border-radius:10px;background:#202020;color:#ff3b3b;font-weight:900;text-align:center;}QToolButton:hover{background:#2a2a2a;color:#ff6a6a;}QToolButton:pressed{background:#303030;}"
def _plus_btn_style():return "QToolButton{padding:0;margin:0;border:1px solid #0b5cff;border-radius:10px;background:#0b5cff;color:#ffffff;font-weight:900;text-align:center;}QToolButton:hover{background:#1266ff;border:1px solid #1266ff;}QToolButton:pressed{background:#0a52e6;border:1px solid #0a52e6;}"
class TagChip(QFrame):
    def __init__(self,text,on_remove,parent=None):
        super().__init__(parent)
        self.setObjectName("TagChip")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        h=QHBoxLayout(self);h.setContentsMargins(8,6,6,6);h.setSpacing(8)
        l=QLabel(text,self);l.setObjectName("TagLabel");l.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        x=QToolButton(self);x.setObjectName("TagXBtn");x.setCursor(Qt.CursorShape.PointingHandCursor);x.setText("X");x.setFixedSize(26,26);x.setStyleSheet(_x_btn_style())
        x.clicked.connect(lambda:on_remove(text))
        h.addWidget(l,1);h.addWidget(x,0)
class RecentTagChip(QFrame):
    def __init__(self,text,on_add,parent=None):
        super().__init__(parent)
        self.setObjectName("RecentTagChip")
        h=QHBoxLayout(self);h.setContentsMargins(8,6,6,6);h.setSpacing(8)
        b=QToolButton(self);b.setObjectName("RecentTagBtn");b.setCursor(Qt.CursorShape.PointingHandCursor);b.setText(text);b.clicked.connect(lambda:on_add(text))
        x=QToolButton(self);x.setObjectName("RecentTagXBtn");x.setCursor(Qt.CursorShape.PointingHandCursor);x.setText("+");x.setFixedSize(26,26);x.setStyleSheet(_plus_btn_style())
        x.clicked.connect(lambda:on_add(text))
        h.addWidget(b,0);h.addWidget(x,0)
class Widget(QWidget):
    command_saved=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("CommandsAddWidget")
        self._skip_confirm=False
        self._tags=[]
        self._dirty=False
        self._last_saved_sig=None
        self._saving=False
        self._edit=False
        self._edit_id=None
        self._external_save=None
        self._dbp=_db_path()
        self._hist=_history_from_db(self._dbp)
        self._suggest=list(self._hist.get("suggest_tags",[]))
        v=QVBoxLayout(self);v.setContentsMargins(0,0,0,0);v.setSpacing(0)
        self.form=QFrame(self);self.form.setObjectName("CmdInlineBox")
        fv=QVBoxLayout(self.form);fv.setContentsMargins(14,8,14,8);fv.setSpacing(8)
        self.warn=QLabel(self.form);self.warn.setObjectName("CmdEditWarning");self.warn.setWordWrap(True);self.warn.setVisible(False)
        fv.addWidget(self.warn,0)
        row1=QGridLayout();row1.setContentsMargins(0,0,0,0);row1.setHorizontalSpacing(8);row1.setVerticalSpacing(8)
        self.cmb_note=QComboBox(self.form);self.cmb_note.setObjectName("CmdNoteName");self.cmb_note.setEditable(True);self.cmb_note.clear()
        self.cmb_cat=QComboBox(self.form);self.cmb_cat.setObjectName("CmdCategory");self.cmb_cat.setEditable(True)
        self.cmb_sub=QComboBox(self.form);self.cmb_sub.setObjectName("CmdSubCategory");self.cmb_sub.setEditable(True)
        for c in (self.cmb_note,self.cmb_cat,self.cmb_sub):c.setMinimumHeight(38);c.setMaximumHeight(38)
        self._fill_combo(self.cmb_note,self._hist.get("notes",[]),self._hist.get("last_note",""))
        self._fill_combo(self.cmb_cat,self._hist.get("categories",[]),self._hist.get("last_category",""))
        self._fill_combo(self.cmb_sub,self._hist.get("subcategories",[]),self._hist.get("last_subcategory",""))
        try:self.cmb_note.lineEdit().setPlaceholderText("Required")
        except:pass
        try:self.cmb_cat.lineEdit().setPlaceholderText("Required")
        except:pass
        try:self.cmb_sub.lineEdit().setPlaceholderText("Required")
        except:pass
        note_wrap=QFrame(self.form);note_wrap.setObjectName("CmdNoteWrap")
        note_l=QHBoxLayout(note_wrap);note_l.setContentsMargins(0,0,0,0);note_l.setSpacing(6)
        self.btn_note_drop=QToolButton(note_wrap);self.btn_note_drop.setObjectName("CmdNoteDrop");self.btn_note_drop.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_note_drop.setText("▼");self.btn_note_drop.setFixedSize(35,35);self.btn_note_drop.setVisible(False)
        note_l.addWidget(self.cmb_note,1);note_l.addWidget(self.btn_note_drop,0,Qt.AlignmentFlag.AlignVCenter)
        cat_wrap=QFrame(self.form);cat_wrap.setObjectName("CmdCategoryWrap")
        cat_l=QHBoxLayout(cat_wrap);cat_l.setContentsMargins(0,0,0,0);cat_l.setSpacing(6)
        self.btn_cat_drop=QToolButton(cat_wrap);self.btn_cat_drop.setObjectName("CmdCategoryDrop");self.btn_cat_drop.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_cat_drop.setText("▼");self.btn_cat_drop.setFixedSize(35,35)
        self.btn_cat_drop.clicked.connect(lambda:self._open_popup(self.cmb_cat))
        cat_l.addWidget(self.cmb_cat,1);cat_l.addWidget(self.btn_cat_drop,0,Qt.AlignmentFlag.AlignVCenter)
        sub_wrap=QFrame(self.form);sub_wrap.setObjectName("CmdSubCategoryWrap")
        sub_l=QHBoxLayout(sub_wrap);sub_l.setContentsMargins(0,0,0,0);sub_l.setSpacing(6)
        self.btn_sub_drop=QToolButton(sub_wrap);self.btn_sub_drop.setObjectName("CmdSubCategoryDrop");self.btn_sub_drop.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_sub_drop.setText("▼");self.btn_sub_drop.setFixedSize(35,35)
        self.btn_sub_drop.clicked.connect(lambda:self._open_popup(self.cmb_sub))
        sub_l.addWidget(self.cmb_sub,1);sub_l.addWidget(self.btn_sub_drop,0,Qt.AlignmentFlag.AlignVCenter)
        self.btn_cat_drop.setVisible(False);self.btn_sub_drop.setVisible(False)
        self.in_desc=QLineEdit(self.form);self.in_desc.setObjectName("CmdBoxDescription");self.in_desc.setPlaceholderText("Optional");self.in_desc.setMaxLength(1024)
        for i in range(4):row1.setColumnStretch(i,1)
        row1.addWidget(QLabel("Command Note Tittle",self.form),0,0);row1.addWidget(QLabel("Category",self.form),0,1);row1.addWidget(QLabel("Sub Category",self.form),0,2);row1.addWidget(QLabel("Description",self.form),0,3)
        row1.addWidget(note_wrap,1,0);row1.addWidget(cat_wrap,1,1);row1.addWidget(sub_wrap,1,2);row1.addWidget(self.in_desc,1,3)
        tags_row=QGridLayout();tags_row.setContentsMargins(0,0,0,0);tags_row.setHorizontalSpacing(8);tags_row.setVerticalSpacing(8)
        self.cmd_tags=QLineEdit(self.form);self.cmd_tags.setObjectName("CmdBoxTags");self.cmd_tags.setPlaceholderText("word,word,word")
        self.in_tag=self.cmd_tags
        self.btn_elements=QToolButton(self.form);self.btn_elements.setObjectName("CmdBoxElements");self.btn_elements.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_elements.setText("Existing Elements");self.btn_elements.setToolTip("Select existing element")
        tags_row.setColumnStretch(0,1);tags_row.setColumnStretch(1,1)
        tags_row.addWidget(QLabel("Tags",self.form),0,0);tags_row.addWidget(QLabel("Elements",self.form),0,1)
        tags_row.addWidget(self.cmd_tags,1,0);tags_row.addWidget(self.btn_elements,1,1)
        for lab in self.form.findChildren(QLabel):lab.setObjectName("CmdBoxLabel")
        self.in_cmd=QTextEdit(self.form);self.in_cmd.setObjectName("CmdBoxCommand");self.in_cmd.setPlaceholderText("Enter command here...")
        self._cmd_cursor=QTextCursor(self.in_cmd.document())
        self.in_cmd.cursorPositionChanged.connect(self._remember_cmd_cursor)
        self.cmd_suggest=_CmdElementSuggest(self.in_cmd,lambda prefix,limit:_target_element_rows(self._dbp,prefix,limit))
        bh=QHBoxLayout();bh.setContentsMargins(0,0,0,0);bh.setSpacing(10)
        self.btn_save=QToolButton(self.form);self.btn_save.setObjectName("CmdSaveBtn");self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_save.setText("");self.btn_save.setToolTip("Save");self.btn_save.setFixedWidth(44)
        si=_abs("..","Assets","Save.png")
        if os.path.isfile(si):self.btn_save.setIcon(QIcon(si));self.btn_save.setIconSize(QSize(18,18))
        fs=self.btn_save.font();fs.setBold(True);fs.setWeight(800);self.btn_save.setFont(fs)
        self.btn_cancel=QToolButton(self.form);self.btn_cancel.setObjectName("CmdCancelBtn");self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_cancel.setText("Cancel")
        fc=self.btn_cancel.font();fc.setBold(True);fc.setWeight(800);self.btn_cancel.setFont(fc)
        self.btn_save.clicked.connect(lambda:self._save(close_after=True))
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_elements.clicked.connect(self._open_cmd_element_picker)
        bh.addStretch(1);bh.addWidget(self.btn_save,0);bh.addWidget(self.btn_cancel,0);bh.addStretch(1)
        fv.addLayout(row1);fv.addLayout(tags_row);fv.addWidget(self.in_cmd,1);fv.addLayout(bh);v.addWidget(self.form,1)
        self._setup_tag_completer()
        self._render_tags()
        self._render_suggest()
        for w in (self.in_desc,self.in_cmd,self.cmd_tags):w.textChanged.connect(self._mark_dirty)
        try:self.cmb_note.lineEdit().textChanged.connect(self._mark_dirty)
        except:pass
        try:self.cmb_cat.lineEdit().textChanged.connect(self._mark_dirty)
        except:pass
        try:self.cmb_sub.lineEdit().textChanged.connect(self._mark_dirty)
        except:pass
        QTimer.singleShot(0,self._bind_close_guard)
        _log("[+]",f"CommandsAdd ready")
    def _open_popup(self,cmb):
        try:cmb.showPopup()
        except:pass
    def _remember_cmd_cursor(self):
        try:self._cmd_cursor=QTextCursor(self.in_cmd.textCursor())
        except Exception:pass
    def _cmd_insert_cursor(self):
        try:
            cur=self.in_cmd.textCursor() if self.in_cmd.hasFocus() else QTextCursor(self._cmd_cursor)
            try:
                if cur.document()!=self.in_cmd.document():cur=self.in_cmd.textCursor()
            except Exception:cur=self.in_cmd.textCursor()
            return cur
        except Exception:
            return self.in_cmd.textCursor()
    def _insert_cmd_element_token(self,token):
        t=_norm_tag(token)
        if not t:return
        raw=t.strip("{}")
        if raw and not t.startswith("{"):t="{"+raw+"}"
        elif raw and not t.endswith("}"):t="{"+raw+"}"
        cur=self._cmd_insert_cursor();cur.insertText(t);self.in_cmd.setTextCursor(cur);self._remember_cmd_cursor();self._dirty=True
        try:self.in_cmd.setFocus()
        except Exception:pass
    def _open_cmd_element_picker(self):
        self._remember_cmd_cursor()
        dlg=_TargetElementPickerDlg(self,self._dbp)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        row=dlg.selected()
        self._insert_cmd_element_token(row.get("token","") or row.get("key",""))
    def set_warning_text(self,text):
        t=_norm_tag(text)
        try:self.warn.setText(t);self.warn.setVisible(bool(t))
        except Exception:pass
    def set_external_save(self,handler):
        self._external_save=handler if callable(handler) else None
    def set_edit_target(self,db_path,nid):
        self._dbp=db_path or self._dbp
        self._edit=True
        self._edit_id=nid
    def set_item(self,item):
        n=item or {}
        self._edit=True
        self._edit_id=n.get("id",n.get("rid",None))
        self.cmb_note.setEditText(_norm_tag(n.get("cmd_note_title","") or n.get("title","") or n.get("note_name","")))
        self.cmb_cat.setEditText(_norm_tag(n.get("category","")))
        self.cmb_sub.setEditText(_norm_tag(n.get("sub","") or n.get("sub_category","")))
        self.in_desc.setText(n.get("description","") or "")
        self.in_cmd.setText(n.get("command","") or "")
        self._tags=_split_tags(n.get("tags",""))
        self._dirty=False
        self._render_tags()
        self._render_suggest()
    def set_prefill(self,item):
        n=item or {}
        self._edit=False
        self._edit_id=None
        if n.get("note_name"):
            self.cmb_note.setEditText(_norm_tag(n.get("note_name","")))
        if n.get("category"):
            self.cmb_cat.setEditText(_norm_tag(n.get("category","")))
        sub=n.get("sub_category") or n.get("sub")
        if sub:
            self.cmb_sub.setEditText(_norm_tag(sub))
        if n.get("description"):
            self.in_desc.setText(n.get("description","") or "")
        if n.get("command"):
            self.in_cmd.setText(n.get("command","") or "")
        self._tags=_split_tags(n.get("tags",""))
        self._dirty=False
        self._render_tags()
        self._render_suggest()
    def export_item(self):
        tags=",".join(_split_tags(self.cmd_tags.text() if hasattr(self,"cmd_tags") else ",".join(self._tags)))
        return {"id":self._edit_id,"note_name":self.cmb_note.currentText().strip(),"category":self.cmb_cat.currentText().strip(),"sub":self.cmb_sub.currentText().strip(),"command":self.in_cmd.toPlainText(),"tags":tags,"description":self.in_desc.text()}
    def _fill_combo(self,cmb,items,last):
        cmb.clear()
        seen=set()
        for x in items:
            t=_norm_tag(x)
            if not t:continue
            k=t.lower()
            if k in seen:continue
            seen.add(k);cmb.addItem(t)
        t=_norm_tag(last)
        if t:
            i=cmb.findText(t,Qt.MatchFlag.MatchFixedString)
            if i>=0:cmb.setCurrentIndex(i)
            else:cmb.setEditText(t)
    def _setup_tag_completer(self):
        tags=[_norm_tag(x) for x in self._hist.get("tags",[]) if _norm_tag(x)]
        self._tag_model=QStringListModel(sorted(set(tags),key=lambda s:s.lower()))
        self._tag_comp=QCompleter(self._tag_model,self)
        self._tag_comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tag_comp.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._tag_comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.in_tag.setCompleter(self._tag_comp)
    def _refresh_tag_model(self):
        tags=[_norm_tag(x) for x in self._hist.get("tags",[]) if _norm_tag(x)]
        self._tag_model.setStringList(sorted(set(tags),key=lambda s:s.lower()))
    def _bind_close_guard(self):
        try:
            w=self.window()
            if w and w is not self:w.installEventFilter(self)
        except:pass
    def eventFilter(self,obj,ev):
        if ev.type()==QEvent.Type.Close:
            if getattr(self,"_skip_confirm",False):
                self._skip_confirm=False
                return False
            r=self._confirm_save()
            if r=="cancel":
                ev.ignore()
                return True
            if r=="save":
                ok=self._save(close_after=True)
                if not ok:
                    ev.ignore()
                    return True
            return False
        return super().eventFilter(obj,ev)
    def _add_tag(self,t):
        t=_norm_tag(t)
        if not t:return
        if any(x.lower()==t.lower() for x in self._tags):return
        self._tags.append(t)
        self._dirty=True
        self._render_tags()
        self._render_suggest()
    def _add_tag_from_input(self):
        self._tags=_split_tags(self.in_tag.text());self._dirty=True;self._render_tags()
    def _remove_tag(self,t):
        tt=_norm_tag(t)
        n=len(self._tags)
        self._tags=[x for x in self._tags if x.lower()!=tt.lower()]
        if len(self._tags)!=n:self._dirty=True
        self._render_tags()
        self._render_suggest()
    def _render_tags(self):
        if not hasattr(self,"cmd_tags"):return
        t=",".join(_split_tags(",".join(self._tags)))
        self.cmd_tags.blockSignals(True);self.cmd_tags.setText(t);self.cmd_tags.blockSignals(False)
    def _clear_layout(self,lay):
        while lay.count():
            it=lay.takeAt(0)
            w=it.widget()
            if w:w.setParent(None);w.deleteLater()
    def _render_suggest(self):
        return
    def _confirm_save(self):
        if not getattr(self,"_dirty",False):return "discard"
        w=self.window() if self.window() else self
        m=QMessageBox(w);m.setWindowTitle("Confirm");m.setText("Do you want to save changes?")
        b_save=m.addButton("Save",QMessageBox.ButtonRole.AcceptRole)
        b_dis=m.addButton("Discard",QMessageBox.ButtonRole.DestructiveRole)
        b_can=m.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        m.setDefaultButton(b_save);m.exec()
        c=m.clickedButton()
        if c==b_save:return "save"
        if c==b_dis:return "discard"
        return "cancel"
    def _cancel(self):
        _log("[*]","Cancel clicked")
        if not getattr(self,"_dirty",False):
            self._close(True);return
        w=self.window() if self.window() else self
        m=QMessageBox(w);m.setWindowTitle("Confirm");m.setText("Do you want to save changes?")
        b_save=m.addButton("Save",QMessageBox.ButtonRole.AcceptRole)
        b_dis=m.addButton("Discard",QMessageBox.ButtonRole.DestructiveRole)
        b_can=m.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
        m.setDefaultButton(b_save);m.exec()
        c=m.clickedButton()
        if c==b_can:return
        if c==b_save:
            ok=self._save(close_after=True)
            if not ok:return
            return
        self._close(True)
    def _close(self,skip_confirm=False):
        try:
            w=self.window()
            if w and w is not self:
                self._skip_confirm=bool(skip_confirm)
                w.close()
        except:pass
    def _sig(self,note_name,cat,sub,desc,cmd,tags):
        s="\n".join([(note_name or "").strip(),(cat or "").strip(),(sub or "").strip(),(desc or "").strip(),(cmd or "").strip(),(tags or "").strip()])
        return hashlib.sha256(s.encode("utf-8","ignore")).hexdigest()
    def _mark_dirty(self,*a):self._dirty=True
    def _refresh_history(self):
        self._hist=_history_from_db(self._dbp)
        self._suggest=list(self._hist.get("suggest_tags",[]))
        self._fill_combo(self.cmb_note,self._hist.get("notes",[]),self.cmb_note.currentText().strip() or self._hist.get("last_note",""))
        self._fill_combo(self.cmb_cat,self._hist.get("categories",[]),self.cmb_cat.currentText().strip() or self._hist.get("last_category",""))
        self._fill_combo(self.cmb_sub,self._hist.get("subcategories",[]),self.cmb_sub.currentText().strip() or self._hist.get("last_subcategory",""))
        self._refresh_tag_model()
        self._render_suggest()
    def _save(self,close_after=False):
        if getattr(self,"_saving",False):return False
        self._saving=True
        self.btn_save.setEnabled(False);self.btn_cancel.setEnabled(False)
        try:
            note_name=_norm_tag(self.cmb_note.currentText())
            cat=_norm_tag(self.cmb_cat.currentText())
            sub=_norm_tag(self.cmb_sub.currentText())
            if not note_name:
                w=self.window() if self.window() else self
                QMessageBox.warning(w,"Missing","Command Note Tittle is required.")
                return False
            if not cat:
                w=self.window() if self.window() else self
                QMessageBox.warning(w,"Missing","Category is required.")
                return False
            if not sub:
                w=self.window() if self.window() else self
                QMessageBox.warning(w,"Missing","Sub Category is required.")
                return False
            desc=self.in_desc.text()
            cmd=self.in_cmd.toPlainText()
            if not _norm_tag(cmd):
                w=self.window() if self.window() else self
                QMessageBox.warning(w,"Missing","Command is required.")
                return False
            tags=",".join(_split_tags(self.cmd_tags.text() if hasattr(self,"cmd_tags") else ",".join(self._tags)))
            self._tags=_split_tags(tags)
            sig=self._sig(note_name,cat,sub,desc,cmd,tags)
            handler=getattr(self,"_external_save",None)
            if callable(handler):
                data={"id":self._edit_id,"note_name":note_name,"category":cat,"sub":sub,"sub_category":sub,"command":cmd,"tags":tags,"description":desc}
                ok=handler(data)
                if not ok:return False
                self._last_saved_sig=sig;self._dirty=False;self._render_tags()
                try:
                    added=_auto_add_target_values(self._dbp or _db_path())
                    if added:_log("[+]",f"Auto-added target elements: {added}")
                except Exception as e:
                    _log("[!]",f"Auto-add target elements failed ({e})")
                try:self.command_saved.emit()
                except:pass
                if close_after:self._close(True)
                return True
            if self._last_saved_sig==sig and not self._dirty:
                if close_after:self._close(True)
                return True
            dbp=self._dbp or _db_path()
            self._dbp=dbp
            if self._edit and self._edit_id is not None:
                ok=_update_cmd(dbp,self._edit_id,note_name,cat,sub,cmd,tags,desc)
                if not ok:
                    w=self.window() if self.window() else self
                    QMessageBox.critical(w,"Error","Failed to update command.")
                    return False
                _log("[+]",f"Updated command (id={self._edit_id})")
            else:
                nid=_insert_cmd(dbp,note_name,cat,sub,cmd,tags,desc)
                self._edit=True
                self._edit_id=nid
                _log("[+]",f"Saved command (id={nid})")
            self._last_saved_sig=sig
            self._dirty=False
            self._refresh_history()
            self._render_tags()
            try:
                added=_auto_add_target_values(dbp)
                if added:_log("[+]",f"Auto-added target elements: {added}")
            except Exception as e:
                _log("[!]",f"Auto-add target elements failed ({e})")
            try:self.command_saved.emit()
            except:pass
            if close_after:self._close(True)
            return True
        except Exception as e:
            _log("[!]",f"Save failed ({e})")
            w=self.window() if self.window() else self
            QMessageBox.critical(w,"Error","Failed to save command.")
            return False
        finally:
            self._saving=False
            self.btn_save.setEnabled(True)
            self.btn_cancel.setEnabled(True)
