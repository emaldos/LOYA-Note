import os,sqlite3,logging,hashlib,re,json,base64,html
from logging.handlers import RotatingFileHandler
from datetime import datetime,timezone
from PyQt6.QtCore import Qt,QSize,QTimer,pyqtSignal,QRect,QEvent,QObject,QStringListModel
from PyQt6.QtGui import QIcon,QKeySequence,QTextCharFormat,QTextListFormat,QTextTableFormat,QTextCursor,QShortcut,QAction,QColor,QTextBlockFormat,QImage,QTextImageFormat,QTextFormat,QTextLength,QTextDocumentFragment,QSyntaxHighlighter,QDrag,QFontMetrics
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QToolButton,QTextEdit,QMessageBox,QDialog,QGridLayout,QSpinBox,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QMenu,QComboBox,QFileDialog,QInputDialog,QSplitter,QCompleter,QListWidget,QApplication,QScrollArea,QButtonGroup,QSizePolicy,QTextBrowser
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
_NOTE_REF_COLOR_DEFAULT="#b197fc"
_NOTE_LINK_COLOR_DEFAULT="#b197fc"
_NOTE_REF_RX=re.compile(r"-Notename-([^\r\n-]+)-",re.I)
_NOTE_LINK_ANCHOR="notelink:"
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
def _kci(s):return _norm(s).lower()
def _targets_values_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"target_values.json")
def _strip_html(s):
    if not s:return ""
    t=str(s)
    t=re.sub(r"(?i)<br\\s*/?>","\n",t)
    t=re.sub(r"(?i)</p>","\n",t)
    t=re.sub(r"(?i)</pre>","\n",t)
    t=re.sub(r"(?i)<pre[^>]*>","",t)
    t=re.sub(r"(?i)<span[^>]*>","",t)
    t=re.sub(r"(?i)</span>","",t)
    t=re.sub(r"<[^>]+>","",t)
    t=html.unescape(t)
    t=t.replace("\r\n","\n").replace("\r","\n")
    lines=[ln.rstrip() for ln in t.split("\n")]
    while lines and not lines[0].strip():lines.pop(0)
    while lines and not lines[-1].strip():lines.pop()
    return "\n".join(lines)
def _note_images_dir():
    d=_abs("..","Data","NoteImages");os.makedirs(d,exist_ok=True)
    return d
def _image_insert_size(iw,ih,max_w=640):
    try:iw=int(iw)
    except:iw=0
    try:ih=int(ih)
    except:ih=0
    if iw<=0 or ih<=0:return 320,240
    if iw>max_w:
        w=max_w
        h=int((ih*w)/iw) if iw else 240
        return max(20,int(w)),max(20,int(h))
    return max(20,int(iw)),max(20,int(ih))
def _save_qimage(img):
    try:
        if img is None or img.isNull():return ""
    except Exception:
        return ""
    base=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name=f"note_{base}.png"
    root=_note_images_dir()
    path=os.path.join(root,name)
    i=1
    while os.path.exists(path):
        path=os.path.join(root,f"note_{base}_{i}.png");i+=1
    try:
        ok=img.save(path,"PNG")
        return path if ok else ""
    except Exception:
        return ""
def _notes_meta_path():
    d=_abs("..","Data");os.makedirs(d,exist_ok=True)
    return os.path.join(d,"notes_meta.json")
def _read_json(p):
    try:
        with open(p,"r",encoding="utf-8") as f:return json.load(f)
    except Exception:
        return None
def _write_json(p,data):
    t=p+".tmp"
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(t,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=True,indent=2)
        os.replace(t,p)
        return True
    except Exception as e:
        _log("[!]",f"JSON write failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False
def _dedupe_ci(items):
    out=[];seen=set()
    for x in items or []:
        t=_norm(x)
        if not t:continue
        k=t.lower()
        if k in seen:continue
        seen.add(k);out.append(t)
    return out
def _load_notes_meta():
    p=_notes_meta_path()
    d=_read_json(p)
    if not isinstance(d,dict):d={}
    pinned=_dedupe_ci(d.get("pinned",[]))
    recent=_dedupe_ci(d.get("recent",[]))
    return {"pinned":pinned,"recent":recent}
def _save_notes_meta(pinned,recent):
    data={"pinned":_dedupe_ci(pinned),"recent":_dedupe_ci(recent)}
    return _write_json(_notes_meta_path(),data)
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
def _write_settings(data):
    global _SETTINGS_CACHE,_SETTINGS_MTIME
    p=_settings_path()
    t=p+".tmp"
    try:
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(t,"w",encoding="utf-8") as f:json.dump(data if isinstance(data,dict) else {},f,ensure_ascii=False,indent=2)
        os.replace(t,p)
        try:_SETTINGS_CACHE=data if isinstance(data,dict) else {}
        except:pass
        try:_SETTINGS_MTIME=os.path.getmtime(p)
        except Exception:_SETTINGS_MTIME=None
        return True
    except Exception as e:
        _log("[!]",f"Settings write failed: {p} ({e})")
        try:
            if os.path.isfile(t):os.remove(t)
        except:pass
        return False

def _norm_hex_color(v):
    s=_norm(v)
    if not s:return ""
    if re.fullmatch(r"#?[0-9a-fA-F]{6}",s):
        return s if s.startswith("#") else "#"+s
    return ""

def _auto_fg_for_bg(hexv):
    color=_norm_hex_color(hexv) or _NOTE_LINK_COLOR_DEFAULT
    h=color.lstrip("#")
    if len(h)!=6:
        return "#000000"
    try:
        r=int(h[0:2],16);g=int(h[2:4],16);b=int(h[4:6],16)
    except Exception:
        return "#000000"
    lum=(0.299*r+0.587*g+0.114*b)/255.0
    return "#000000" if lum>0.6 else "#ffffff"

def _note_ref_color():
    s=_read_settings()
    c=_norm_hex_color(s.get("note_ref_color","") if isinstance(s,dict) else "")
    return c or _NOTE_REF_COLOR_DEFAULT

def _set_note_ref_color_setting(hexv):
    s=_read_settings()
    if not isinstance(s,dict):s={}
    if hexv:s["note_ref_color"]=hexv
    else:s.pop("note_ref_color",None)
    _write_settings(s)

def _iter_note_refs(text):
    t=text or ""
    for m in _NOTE_REF_RX.finditer(t):
        raw=m.group(1) or ""
        if not raw:continue
        name=raw.strip()
        if not name:continue
        start=m.start(1)
        ltrim=len(raw)-len(raw.lstrip())
        rtrim=len(raw.rstrip())
        if rtrim<=ltrim:continue
        yield name,start+ltrim,start+rtrim

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
        nk=_norm(k)
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
def _target_key_list():
    keys,_,_=_load_target_priorities()
    return list(keys.keys())
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
                k=_norm(m.group(1))
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
    if added>0 or dupe:_write_target_priorities(pri)
    return added
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
def _encode_note_link_data(note,color):
    d={"note":_norm(note),"color":_norm_hex_color(color)}
    raw=json.dumps(d,ensure_ascii=False)
    b=base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")
    return b.rstrip("=")
def _decode_note_link_data(token):
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
def _fmt_note_time(t):
    raw=_norm(t)
    if not raw:return ""
    dt=None
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S"):
            try:
                dt=datetime.strptime(raw[:19],fmt)
                break
            except Exception:
                dt=None
    if not dt:return raw.replace("T"," ")[:19]
    try:dt=dt.astimezone()
    except Exception:pass
    return dt.strftime("%H:%M %d/%m/%Y")
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
class _CreateNoteDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("NoteAddDialog")
        self.setWindowTitle("Create Note")
        self.resize(980,720)
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        root=QVBoxLayout(self);root.setContentsMargins(14,14,14,14);root.setSpacing(12)
        self.body=QFrame(self);self.body.setObjectName("NoteAddFrame")
        root.addWidget(self.body,1)
        self.body_layout=QVBoxLayout(self.body);self.body_layout.setContentsMargins(10,10,10,10);self.body_layout.setSpacing(0)
    def closeEvent(self,e):
        try:
            owner=self.parent()
            if owner and hasattr(owner,"_on_create_dialog_closed"):
                owner._on_create_dialog_closed()
        except Exception:
            pass
        try:super().closeEvent(e)
        except Exception:pass
class _NoteLinkDlg(QDialog):
    def __init__(self,parent,notes,title_value="",note_value="",color_value=""):
        super().__init__(parent)
        self.setObjectName("NoteAddDialog")
        self.setWindowTitle("Add Link")
        self.resize(620,520)
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        self._notes=[_norm(n) for n in (notes or []) if _norm(n)]
        self._notes=sorted(list(dict.fromkeys(self._notes)),key=lambda s:s.lower())
        self._view=[]
        self._color=_norm_hex_color(color_value) or _NOTE_LINK_COLOR_DEFAULT
        root=QVBoxLayout(self);root.setContentsMargins(14,14,14,14);root.setSpacing(12)
        box=QFrame(self);box.setObjectName("TargetDialogFrame")
        v=QVBoxLayout(box);v.setContentsMargins(12,12,12,12);v.setSpacing(10)
        head=QHBoxLayout();head.setSpacing(10)
        t=QLabel("Note Link",box);t.setObjectName("TargetFormTitle")
        head.addWidget(t,1)
        v.addLayout(head)
        g=QGridLayout();g.setContentsMargins(0,0,0,0);g.setHorizontalSpacing(12);g.setVerticalSpacing(10)
        self.in_title=QLineEdit(box);self.in_title.setObjectName("CmdBoxNoteTitle");self.in_title.setPlaceholderText("Button title");self.in_title.setText((title_value or "").strip())
        self.in_note=QLineEdit(box);self.in_note.setObjectName("CmdBoxNoteTitle");self.in_note.setPlaceholderText("Choose note");self.in_note.setText((note_value or "").strip())
        self.btn_color=QToolButton(box);self.btn_color.setObjectName("NoteLinkColor");self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_color.setText("Color")
        self.btn_color.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        cm=QMenu(self.btn_color)
        for name,hexv in (("Default",None),("Light Purple","#b197fc"),("Blue","#4dabf7"),("Green","#8ce99a"),("Yellow","#ffd43b"),("Orange","#ff922b"),("Red","#ff6b6b"),("White","#ffffff"),("Black","#000000")):
            a=QAction(name,self.btn_color);a.triggered.connect(lambda chk=False,v=hexv:self._set_color(v));cm.addAction(a)
        cm.addSeparator()
        ac=QAction("Custom...",self.btn_color);ac.triggered.connect(self._custom_color);cm.addAction(ac)
        self.btn_color.setMenu(cm)
        g.addWidget(QLabel("Button Title",box),0,0);g.addWidget(self.in_title,0,1,1,2)
        g.addWidget(QLabel("Note",box),1,0);g.addWidget(self.in_note,1,1,1,2)
        g.addWidget(QLabel("Color",box),2,0);g.addWidget(self.btn_color,2,1,1,2)
        v.addLayout(g)
        self.search=QLineEdit(box);self.search.setObjectName("NoteAddSearch");self.search.setPlaceholderText("Search notes...")
        self.search.textChanged.connect(self._render_notes)
        v.addWidget(self.search,0)
        self.list_wrap=QFrame(box);self.list_wrap.setObjectName("NoteAddTableFrame")
        lw=QVBoxLayout(self.list_wrap);lw.setContentsMargins(10,10,10,10);lw.setSpacing(6)
        self.tbl=QTableWidget(self.list_wrap);self.tbl.setObjectName("NoteAddTable")
        self.tbl.setColumnCount(1);self.tbl.setHorizontalHeaderLabels(["Note"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(False)
        self.tbl.cellClicked.connect(self._pick_note)
        self.tbl.cellDoubleClicked.connect(lambda r,c:self._pick_note(r,c,accept=True))
        h=self.tbl.horizontalHeader();h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter);h.setStretchLastSection(True)
        lw.addWidget(self.tbl,1)
        v.addWidget(self.list_wrap,1)
        b=QHBoxLayout();b.setContentsMargins(0,0,0,0);b.setSpacing(10)
        self.ok=QToolButton(box);self.ok.setObjectName("TableOk");self.ok.setCursor(Qt.CursorShape.PointingHandCursor);self.ok.setText("Insert")
        self.ca=QToolButton(box);self.ca.setObjectName("TableCancel");self.ca.setCursor(Qt.CursorShape.PointingHandCursor);self.ca.setText("Cancel")
        self.ok.clicked.connect(self._ok);self.ca.clicked.connect(self.reject)
        b.addStretch(1);b.addWidget(self.ok,0);b.addWidget(self.ca,0);b.addStretch(1)
        v.addLayout(b)
        root.addWidget(box,1)
        if self._notes:
            model=QStringListModel(self._notes,self.in_note)
            comp=QCompleter(model,self.in_note)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            self.in_note.setCompleter(comp)
        if not self.in_title.text().strip() and self.in_note.text().strip():
            self.in_title.setText(self.in_note.text().strip())
        self._apply_color_btn()
        self._render_notes()
    def _apply_color_btn(self):
        color=_norm_hex_color(self._color) or _NOTE_LINK_COLOR_DEFAULT
        fg=_auto_fg_for_bg(color)
        self.btn_color.setStyleSheet(f"QToolButton#NoteLinkColor{{background:{color};color:{fg};border:1px solid #2b2b2b;border-radius:8px;padding:2px 8px;}}")
    def _set_color(self,hexv):
        self._color=_norm_hex_color(hexv) or _NOTE_LINK_COLOR_DEFAULT
        self._apply_color_btn()
    def _custom_color(self):
        val,ok=QInputDialog.getText(self,"Custom Color","Hex color (#RRGGBB):",text=_norm_hex_color(self._color) or _NOTE_LINK_COLOR_DEFAULT)
        if not ok:return
        c=_norm_hex_color(val)
        if not c:
            QMessageBox.warning(self,"Invalid","Enter a valid hex color like #b197fc.")
            return
        self._color=c
        self._apply_color_btn()
    def _render_notes(self):
        q=_norm(self.search.text()).lower()
        self._view=[n for n in self._notes if not q or q in n.lower()]
        self.tbl.setRowCount(len(self._view))
        for i,n in enumerate(self._view):
            it=QTableWidgetItem(n);it.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            self.tbl.setItem(i,0,it)
            self.tbl.setRowHeight(i,36)
        self.tbl.clearSelection()
        self._sync_selection()
    def _sync_selection(self):
        nm=_norm(self.in_note.text())
        if not nm:return
        for i,n in enumerate(self._view):
            if n.lower()==nm.lower():
                self.tbl.selectRow(i)
                break
    def _pick_note(self,row,col,accept=False):
        if row<0 or row>=len(self._view):return
        note=self._view[row]
        prev=_norm(self.in_note.text())
        self.in_note.setText(note)
        title=self.in_title.text().strip()
        if not title or title==prev:
            self.in_title.setText(note)
        if accept:self._ok()
    def _ok(self):
        title=(self.in_title.text() or "").replace("\r","\n").replace("\n"," ").strip()
        note=_norm(self.in_note.text())
        if not note:
            QMessageBox.warning(self,"Missing","Note is required.")
            return
        if self._notes and not any(note.lower()==n.lower() for n in self._notes):
            QMessageBox.warning(self,"Missing","Choose a note from the list.")
            return
        if not title:
            title=note
            self.in_title.setText(title)
        self._vals={"title":title,"note":note,"color":_norm_hex_color(self._color) or _NOTE_LINK_COLOR_DEFAULT}
        self.accept()
    def vals(self):return self._vals
class _CmdBlockDlg(QDialog):
    def __init__(self,parent,title_value="",key_list_fn=None):
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
class _PlaceholderHighlighter(QSyntaxHighlighter):
    def __init__(self,doc):
        super().__init__(doc)
        self._known=set()
        self._fmt_ok=QTextCharFormat()
        self._fmt_ok.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
        self._fmt_ok.setUnderlineColor(QColor("#4dabf7"))
        self._fmt_unknown=QTextCharFormat()
        self._fmt_unknown.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DotLine)
        self._fmt_unknown.setUnderlineColor(QColor("#ffd43b"))
        self._fmt_bad=QTextCharFormat()
        self._fmt_bad.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self._fmt_bad.setUnderlineColor(QColor("#ff6b6b"))
        self._ref_fmt=QTextCharFormat()
        self.set_note_ref_color(_note_ref_color())
    def set_known(self,keys):
        self._known={_kci(k) for k in (keys or []) if _norm(k)}
        self.rehighlight()
    def set_note_ref_color(self,hexv):
        c=_norm_hex_color(hexv) or _NOTE_REF_COLOR_DEFAULT
        self._ref_fmt=QTextCharFormat()
        self._ref_fmt.setForeground(QColor(c))
        self.rehighlight()
    def highlightBlock(self,text):
        if not text:return
        for m in re.finditer(r"\{([^{}\r\n]+)\}",text):
            raw=_norm(m.group(1))
            if not raw:continue
            if not _is_valid_key(raw):
                fmt=self._fmt_bad
            elif _kci(raw) in self._known:
                fmt=self._fmt_ok
            else:
                fmt=self._fmt_unknown
            self.setFormat(m.start(),m.end()-m.start(),fmt)
        for _,start,end in _iter_note_refs(text):
            self.setFormat(start,end-start,self._ref_fmt)
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
        keys=[_norm(k) for k in keys if _norm(k)]
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
        if not re.match(r"^[A-Za-z0-9_\\-.:]*$",prefix):return None
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
class _CmdPickerDlg(QDialog):
    def __init__(self,parent,dbp):
        super().__init__(parent)
        self.setObjectName("CmdPickerDialog")
        self.setWindowTitle("Pick Command")
        self.resize(980,600)
        ico=_abs("..","Assets","logox.png")
        if os.path.isfile(ico):self.setWindowIcon(QIcon(ico))
        self._rows=self._load_rows(dbp)
        root=QVBoxLayout(self);root.setContentsMargins(14,14,14,14);root.setSpacing(10)
        top=QHBoxLayout();top.setContentsMargins(0,0,0,0);top.setSpacing(10)
        self.search=QLineEdit(self);self.search.setObjectName("CmdPickerSearch");self.search.setPlaceholderText("Search commands...")
        self.search.textChanged.connect(self._render)
        top.addWidget(self.search,1)
        root.addLayout(top)
        self.tbl=QTableWidget(self);self.tbl.setObjectName("CmdPickerTable")
        self.tbl.setColumnCount(5)
        self.tbl.setHorizontalHeaderLabels(["Note","Title","Category","Sub","Command"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(False)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setShowGrid(True)
        self.tbl.cellDoubleClicked.connect(lambda r,c:self._accept_row(r))
        h=self.tbl.horizontalHeader()
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        fh=h.font();fh.setBold(True);fh.setWeight(800);h.setFont(fh)
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.tbl,1)
        bh=QHBoxLayout();bh.setContentsMargins(0,0,0,0);bh.setSpacing(10)
        self.btn_ok=QToolButton(self);self.btn_ok.setObjectName("CmdSaveBtn");self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ok.setText("Insert")
        self.btn_ca=QToolButton(self);self.btn_ca.setObjectName("CmdCancelBtn");self.btn_ca.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ca.setText("Cancel")
        self.btn_ok.clicked.connect(self._accept_selected)
        self.btn_ca.clicked.connect(self.reject)
        bh.addStretch(1);bh.addWidget(self.btn_ok,0);bh.addWidget(self.btn_ca,0)
        root.addLayout(bh)
        self._selected=None
        self._render()
    def _snip(self,s,n=90):
        t=_norm(s)
        return t if len(t)<=n else t[:max(0,n-3)]+"..."
    def _load_rows(self,dbp):
        rows=[]
        if not dbp or not os.path.isfile(dbp):return rows
        con=None
        try:
            con=sqlite3.connect(dbp,timeout=5)
            cur=con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Commands'")
            if not cur.fetchone():return rows
            cols=set(_table_cols(cur,"Commands"))
            need=["id","note_name","cmd_note_title","category","sub_category","tags","description","command"]
            sel=[c for c in need if c in cols]
            if "id" not in sel:sel.insert(0,"rowid as id")
            cur.execute("SELECT "+",".join(sel)+" FROM Commands")
            for r in cur.fetchall():
                item={}
                for i,c in enumerate(sel):
                    key=c.split(" as ")[-1]
                    item[key]=r[i] if i<len(r) else ""
                if not _norm(item.get("command","")):continue
                item["command_plain"]=_strip_html(item.get("command",""))
                rows.append(item)
        except Exception:
            return rows
        finally:
            try:
                if con:con.close()
            except Exception:
                pass
        return rows
    def _match(self,row,q):
        if not q:return True
        blob=" ".join([
            row.get("note_name",""),
            row.get("cmd_note_title",""),
            row.get("category",""),
            row.get("sub_category",""),
            row.get("tags",""),
            row.get("description",""),
            row.get("command_plain","") or row.get("command",""),
        ]).lower()
        return q in blob
    def _render(self):
        q=_norm(self.search.text()).lower()
        rows=[r for r in self._rows if self._match(r,q)]
        self.tbl.setRowCount(len(rows))
        for i,row in enumerate(rows):
            note=_norm(row.get("note_name",""))
            title=_norm(row.get("cmd_note_title","")) or note
            cat=_norm(row.get("category",""))
            sub=_norm(row.get("sub_category",""))
            cmd=self._snip(row.get("command_plain","") or row.get("command",""))
            it0=QTableWidgetItem(note);it0.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it0.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            it1=QTableWidgetItem(title);it1.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it1.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            it2=QTableWidgetItem(cat);it2.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it3=QTableWidgetItem(sub);it3.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it4=QTableWidgetItem(cmd);it4.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);it4.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            it4.setToolTip(_norm(row.get("command_plain","") or row.get("command","")))
            it0.setData(Qt.ItemDataRole.UserRole,row)
            self.tbl.setItem(i,0,it0);self.tbl.setItem(i,1,it1);self.tbl.setItem(i,2,it2);self.tbl.setItem(i,3,it3);self.tbl.setItem(i,4,it4)
            self.tbl.setRowHeight(i,42)
        self.tbl.clearSelection()
    def _accept_row(self,row):
        it=self.tbl.item(row,0)
        if not it:return
        data=it.data(Qt.ItemDataRole.UserRole)
        if isinstance(data,dict):
            self._selected=data
            self.accept()
    def _accept_selected(self):
        row=self.tbl.currentRow()
        if row>=0:self._accept_row(row)
    def selected(self):
        return self._selected
class NoteEdit(QTextEdit):
    def __init__(self,on_add_cmd,on_enter,on_cmd_anchor=None,is_cmd_table=None,on_note_ref=None,on_note_link=None,on_note_link_edit=None,parent=None):
        super().__init__(parent)
        self._on_add_cmd=on_add_cmd
        self._on_enter=on_enter
        self._on_cmd_anchor=on_cmd_anchor
        self._on_note_ref=on_note_ref
        self._on_note_link=on_note_link
        self._on_note_link_edit=on_note_link_edit
        self._is_cmd_table=is_cmd_table if callable(is_cmd_table) else (lambda _t: False)
        self._img_resize_active=False
        self._img_resize_pos=None
        self._img_resize_start=None
        self._img_resize_base=None
        self._img_resize_ratio=1.0
        self._active_img_pos=None
        self._link_click_info=None
        self._link_click_pos=None
        self._link_dragging=False
        self._link_drag_move=None
        self._link_drag_drop_pos=None
        self.setObjectName("NoteArea")
        self.setAcceptRichText(True)
        self.setAcceptDrops(True)
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
        self._img_tool=QFrame(self.viewport())
        self._img_tool.setObjectName("NoteImageTool")
        ih=QHBoxLayout(self._img_tool);ih.setContentsMargins(6,4,6,4);ih.setSpacing(6)
        self._img_minus=QToolButton(self._img_tool);self._img_minus.setObjectName("NoteImageMinus");self._img_minus.setText("-")
        self._img_plus=QToolButton(self._img_tool);self._img_plus.setObjectName("NoteImagePlus");self._img_plus.setText("+")
        self._img_fit=QToolButton(self._img_tool);self._img_fit.setObjectName("NoteImageFit");self._img_fit.setText("Fit")
        for b in (self._img_minus,self._img_plus,self._img_fit):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoRaise(True)
        self._img_minus.clicked.connect(lambda:self._scale_active_image(0.9))
        self._img_plus.clicked.connect(lambda:self._scale_active_image(1.1))
        self._img_fit.clicked.connect(self._fit_active_image)
        ih.addWidget(self._img_minus,0);ih.addWidget(self._img_plus,0);ih.addWidget(self._img_fit,0)
        self._img_tool.hide()
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
        if not cursor.hasSelection() and key in (Qt.Key.Key_Backspace,Qt.Key.Key_Delete):
            pos=cursor.position()
            info=None
            if key==Qt.Key.Key_Backspace and pos>0:
                info=self._note_link_info_at_pos(pos-1)
            elif key==Qt.Key.Key_Delete:
                info=self._note_link_info_at_pos(pos)
            if info:
                self._delete_note_link(info)
                e.accept()
                return
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
        click=self.cursorForPosition(e.pos())
        cur=self.textCursor()
        if cur.hasSelection():
            s=cur.selectionStart();t=cur.selectionEnd()
            pos=click.position()
            if pos<s or pos>t:self.setTextCursor(click)
        else:
            self.setTextCursor(click)
        m=self.createStandardContextMenu()
        for a in list(m.actions()):
            t=(a.text() or "").lower()
            if "unicode" in t:m.removeAction(a)
        table=click.currentTable()
        if table and self._is_cmd_table(table):
            m.addSeparator()
            a=m.addAction("Copy Command")
            a.triggered.connect(lambda:self._copy_cmd_table(table))
        info=self._note_link_info_at_pos(click.position())
        if info:
            m.addSeparator()
            a=m.addAction("Edit Link")
            a.triggered.connect(lambda:self._edit_note_link(info))
            d=m.addAction("Delete Link")
            d.triggered.connect(lambda:self._delete_note_link(info))
        m.addSeparator()
        a=m.addAction("Add Command Here")
        a.triggered.connect(lambda:self._on_add_cmd(True))
        m.exec(e.globalPos())
    def _copy_cmd_table(self,table):
        if not table:return
        try:
            cell=table.cellAt(0,0)
            c=cell.firstCursorPosition()
            c.setPosition(cell.lastCursorPosition().position(),QTextCursor.MoveMode.KeepAnchor)
            txt=c.selectedText().replace("\u2029","\n")
            QApplication.clipboard().setText(txt)
        except Exception:
            pass
    def eventFilter(self,obj,event):
        if obj is self._tbl_tool and event.type()==QEvent.Type.ContextMenu:
            self._show_table_menu()
            return True
        return super().eventFilter(obj,event)
    def _mime_has_image(self,md):
        try:
            if md.hasImage():return True
            if md.hasUrls():
                for u in md.urls():
                    p=u.toLocalFile()
                    if not p or not os.path.isfile(p):continue
                    ext=os.path.splitext(p)[1].lower()
                    if ext in (".png",".jpg",".jpeg",".bmp",".gif",".webp"):return True
        except Exception:
            return False
        return False
    def _insert_image_path(self,path,qimg=None):
        if not path:return False
        iw=ih=0
        try:
            if qimg is not None and not qimg.isNull():
                iw=qimg.width();ih=qimg.height()
        except Exception:
            iw=ih=0
        w,h=_image_insert_size(iw,ih)
        cur=self.textCursor()
        fmt=QTextImageFormat();fmt.setName(path);fmt.setWidth(float(w));fmt.setHeight(float(h))
        cur.insertImage(fmt)
        self._center_block_at_cursor(cur)
        self.setTextCursor(cur)
        return True
    def _insert_image_from_mime(self,md):
        try:
            if md.hasImage():
                raw=md.imageData()
                if isinstance(raw,QImage):qimg=raw
                elif hasattr(raw,"toImage"):qimg=raw.toImage()
                else:qimg=QImage(raw)
                path=_save_qimage(qimg)
                return self._insert_image_path(path,qimg)
            if md.hasUrls():
                inserted=False
                for u in md.urls():
                    p=u.toLocalFile()
                    if not p or not os.path.isfile(p):continue
                    qimg=QImage(p)
                    if qimg.isNull():continue
                    path=_save_qimage(qimg)
                    if not path:continue
                    if inserted:
                        cur=self.textCursor()
                        cur.insertBlock()
                        self.setTextCursor(cur)
                    if self._insert_image_path(path,qimg):inserted=True
                return inserted
        except Exception:
            return False
        return False
    def canInsertFromMimeData(self,source):
        if self._mime_has_image(source):return True
        return super().canInsertFromMimeData(source)
    def insertFromMimeData(self,source):
        if self._insert_image_from_mime(source):return
        super().insertFromMimeData(source)
    def dragEnterEvent(self,e):
        if self._mime_has_image(e.mimeData()):
            e.acceptProposedAction()
            return
        super().dragEnterEvent(e)
    def dropEvent(self,e):
        if self._link_drag_move and e.source() is self:
            try:self._link_drag_drop_pos=self.cursorForPosition(e.position().toPoint()).position()
            except Exception:self._link_drag_drop_pos=None
        if self._insert_image_from_mime(e.mimeData()):
            e.acceptProposedAction()
            return
        super().dropEvent(e)
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
    def _note_ref_at_pos(self,pos):
        try:
            cur=self.cursorForPosition(pos)
            block=cur.block()
            if not block.isValid():return ""
            text=block.text()
            if not text:return ""
            idx=cur.position()-block.position()
            for name,start,end in _iter_note_refs(text):
                if idx>=start and idx<=end:
                    return name
        except Exception:
            return ""
        return ""
    def _note_link_info_at_pos(self,pos):
        try:
            doc=self.document()
            if pos is None or pos<0 or pos>=doc.characterCount():return None
            block=doc.findBlock(pos)
            if not block.isValid():return None
            parts=[]
            it=block.begin()
            while not it.atEnd():
                frag=it.fragment()
                if frag.isValid():
                    fmt=frag.charFormat()
                    if fmt.isAnchor():
                        href=fmt.anchorHref() or ""
                        if href.startswith(_NOTE_LINK_ANCHOR):
                            start=frag.position()
                            end=start+frag.length()
                            parts.append((start,end,frag.text(),href))
                it+=1
            target=None
            for start,end,_,href in parts:
                if pos>=start and pos<end:
                    target=href
                    break
            if not target:return None
            segs=[(s,e,t) for s,e,t,h in parts if h==target]
            if not segs:return None
            segs.sort(key=lambda x:x[0])
            title="".join(t for _,_,t in segs)
            start=min(s for s,_,_ in segs);end=max(e for _,e,_ in segs)
            data=_decode_note_link_data(target[len(_NOTE_LINK_ANCHOR):])
            note=_norm(data.get("note",""))
            color=_norm_hex_color(data.get("color",""))
            return {"start":start,"end":end,"note":note,"color":color,"title":title,"href":target}
        except Exception:
            return None
    def _note_link_format(self,note,color):
        nm=_norm(note)
        c=_norm_hex_color(color) or _NOTE_LINK_COLOR_DEFAULT
        token=_encode_note_link_data(nm,c)
        fmt=QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(_NOTE_LINK_ANCHOR+token)
        fmt.setBackground(QColor(c))
        fmt.setForeground(QColor(_auto_fg_for_bg(c)))
        fmt.setFontWeight(800)
        fmt.setFontUnderline(False)
        return fmt
    def insert_note_link(self,note,title,color,cursor=None):
        nm=_norm(note)
        if not nm:return False
        t=str(title or nm).replace("\r","\n").replace("\n"," ").strip()
        if not t:t=nm
        cur=cursor if cursor is not None else self.textCursor()
        try:
            tb=cur.currentTable()
            if tb and self._is_cmd_table(tb):
                cur=QTextCursor(self.document())
                cur.setPosition(tb.lastCursorPosition().position()+1)
        except Exception:
            pass
        fmt=self._note_link_format(nm,color)
        cur.beginEditBlock()
        if cur.hasSelection():cur.removeSelectedText()
        cur.insertText(t,fmt)
        cur.endEditBlock()
        self.setTextCursor(cur)
        return True
    def _replace_note_link(self,info,note,title,color):
        if not info:return False
        nm=_norm(note) or _norm(info.get("note",""))
        if not nm:return False
        t=str(title or nm).replace("\r","\n").replace("\n"," ").strip()
        if not t:t=nm
        fmt=self._note_link_format(nm,color)
        cur=QTextCursor(self.document())
        cur.beginEditBlock()
        cur.setPosition(info["start"])
        cur.setPosition(info["end"],QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(t,fmt)
        cur.endEditBlock()
        self.setTextCursor(cur)
        return True
    def _delete_note_link(self,info):
        if not info:return False
        cur=QTextCursor(self.document())
        cur.beginEditBlock()
        cur.setPosition(info["start"])
        cur.setPosition(info["end"],QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.endEditBlock()
        self.setTextCursor(cur)
        return True
    def _edit_note_link(self,info):
        if not info or not callable(self._on_note_link_edit):return
        data={"note":info.get("note",""),"title":info.get("title",""),"color":info.get("color","")}
        out=self._on_note_link_edit(data)
        if not isinstance(out,dict):return
        note=out.get("note","") or info.get("note","")
        title=out.get("title","") or ""
        color=out.get("color","") or info.get("color","")
        self._replace_note_link(info,note,title,color)
    def _start_link_drag(self,info):
        if not info:return
        doc=self.document()
        cur=QTextCursor(doc)
        cur.setPosition(info["start"])
        cur.setPosition(info["end"],QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cur)
        md=self.createMimeDataFromSelection()
        drag=QDrag(self)
        drag.setMimeData(md)
        self._link_drag_move={"start":info["start"],"end":info["end"]}
        self._link_drag_drop_pos=None
        act=drag.exec(Qt.DropAction.MoveAction|Qt.DropAction.CopyAction,Qt.DropAction.MoveAction)
        if act==Qt.DropAction.MoveAction and self._link_drag_drop_pos is not None:
            self._finalize_link_drag(self._link_drag_move,self._link_drag_drop_pos)
        self._link_drag_move=None
        self._link_drag_drop_pos=None
    def _finalize_link_drag(self,info,drop_pos):
        if not info or drop_pos is None:return
        start=int(info.get("start",0));end=int(info.get("end",0))
        if end<=start:return
        if drop_pos>start and drop_pos<end:
            return
        length=end-start
        if drop_pos<=start:
            start+=length;end+=length
        cur=QTextCursor(self.document())
        cur.beginEditBlock()
        cur.setPosition(start)
        cur.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.endEditBlock()
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
        self._center_block_at_cursor(c)
    def _center_block_at_cursor(self,cur):
        try:
            bf=QTextBlockFormat();bf.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cur.mergeBlockFormat(bf)
        except Exception:
            pass
    def _image_at_pos(self,pos):
        doc=self.document()
        if pos is None or pos<0 or pos>=doc.characterCount():return None,None
        cur=QTextCursor(doc)
        cur.setPosition(int(pos))
        fmt=cur.charFormat()
        if not fmt.isImageFormat():return None,None
        return cur,fmt.toImageFormat()
    def _current_image_size(self,img):
        w=img.width();h=img.height()
        if w<=0 or h<=0:
            qimg=QImage(img.name())
            if not qimg.isNull():
                w=qimg.width();h=qimg.height()
        return int(w),int(h)
    def _hide_image_tool(self):
        try:self._img_tool.hide()
        except Exception:pass
        self._active_img_pos=None
    def _show_image_tool(self,cur,img,rect):
        if not cur or not img or rect.isNull():
            self._hide_image_tool()
            return
        try:
            self._active_img_pos=cur.position()
            self._img_tool.adjustSize()
            x=rect.right()-self._img_tool.width()
            y=rect.top()-self._img_tool.height()-6
            if y<0:y=rect.bottom()+6
            if x<0:x=0
            self._img_tool.move(x,y)
            self._img_tool.show()
        except Exception:
            self._hide_image_tool()
    def _scale_active_image(self,factor):
        cur,img=self._image_at_pos(self._active_img_pos)
        if not cur or not img:return
        w,h=self._current_image_size(img)
        if w<=0 or h<=0:return
        nw=max(20,int(w*factor))
        nh=max(20,int(h*factor))
        self._apply_image_size(cur.position(),nw,nh)
        rect=self.cursorRect(cur)
        self._show_image_tool(cur,img,rect)
    def _fit_active_image(self):
        cur,img=self._image_at_pos(self._active_img_pos)
        if not cur or not img:return
        w,h=self._current_image_size(img)
        if w<=0 or h<=0:return
        nw,nh=_image_insert_size(w,h,640)
        self._apply_image_size(cur.position(),nw,nh)
        rect=self.cursorRect(cur)
        self._show_image_tool(cur,img,rect)
    def mousePressEvent(self,e):
        self._img_resize_active=False
        self._link_click_info=None
        self._link_click_pos=None
        self._link_dragging=False
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
        if e.button()==Qt.MouseButton.LeftButton:
            info=self._note_link_info_at_pos(self.cursorForPosition(e.pos()).position())
            if info:
                self._link_click_info=info
                self._link_click_pos=e.position().toPoint()
        if e.button()==Qt.MouseButton.LeftButton and not self._link_click_info:
            ref=self._note_ref_at_pos(e.position().toPoint())
            if ref and callable(self._on_note_ref):
                try:
                    if self._on_note_ref(ref):
                        e.accept()
                        return
                except Exception:
                    pass
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
                self._show_image_tool(cur,img,rect)
            else:
                cur2,img2,rect2=self._image_rect_at(pos)
                if cur2 and img2:self._show_image_tool(cur2,img2,rect2)
                else:self._hide_image_tool()
        super().mousePressEvent(e)
        if self._link_click_info and e.button()==Qt.MouseButton.LeftButton:
            try:
                cur=QTextCursor(self.document())
                cur.setPosition(self._link_click_info["start"])
                cur.setPosition(self._link_click_info["end"],QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cur)
            except Exception:
                pass
    def mouseMoveEvent(self,e):
        pos=e.position().toPoint()
        if self._link_click_info and (e.buttons()&Qt.MouseButton.LeftButton):
            try:
                dist=(pos-self._link_click_pos).manhattanLength()
                if dist>=QApplication.startDragDistance():
                    if not self._link_dragging:
                        self._link_dragging=True
                        self._start_link_drag(self._link_click_info)
                    e.accept()
                    return
            except Exception:
                pass
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
                cur2,img2=self._image_at_pos(self._img_resize_pos)
                if cur2 and img2:self._show_image_tool(cur2,img2,self.cursorRect(cur2))
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
            elif href and href.startswith(_NOTE_LINK_ANCHOR):
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                ref=self._note_ref_at_pos(pos)
                if ref:self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                else:self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(e)
    def mouseReleaseEvent(self,e):
        if self._img_resize_active:self._img_resize_active=False
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        if self._link_click_info and not self._link_dragging and e.button()==Qt.MouseButton.LeftButton:
            try:
                note=_norm(self._link_click_info.get("note",""))
                if note and callable(self._on_note_link):self._on_note_link(note)
            except Exception:
                pass
        self._link_click_info=None
        self._link_click_pos=None
        self._link_dragging=False
        super().mouseReleaseEvent(e)
class Widget(QWidget):
    note_saved=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("NoteWidget")
        self._saving=False
        self._dirty=False
        self._last_sig=None
        self._current_font_size=_DEFAULT_FONT_SIZE
        self._dbp=_db_path()
        self._notes_cache=[]
        self._list_view=[];self._list_page=1;self._list_per=10
        self._note_id=None;self._orig_name=None
        self._cmd_edit_table=None
        self._placeholder_keys=set()
        self._placeholder_key_list=[]
        self._targets_mtime=None
        meta=_load_notes_meta()
        self._pinned=list(meta.get("pinned",[]))
        self._recent=[]
        self._toast=None;self._toast_msg=None
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        self.frame=QFrame(self);self.frame.setObjectName("NoteFrame");root.addWidget(self.frame,1)
        v=QVBoxLayout(self.frame);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        self.tabs=QTabWidget(self.frame);self.tabs.setObjectName("TargetTabs")
        v.addWidget(self.tabs,1)
        self.tab_nav=QWidget();self.tab_nav.setObjectName("Page")
        self.tab_list=QWidget();self.tab_list.setObjectName("Page")
        self.tabs.addTab(self.tab_nav,"Navigate")
        self.tabs.addTab(self.tab_list,"Notes Manager")
        self._build_nav()
        self._build_list()
        try:self._render_nav_list(force=True)
        except Exception:pass
        try:self._render_list()
        except Exception:pass
        self.tab_create=QWidget(self);self.tab_create.setObjectName("Page");self.tab_create.hide()
        self._build_create()
        self._create_holder=QFrame(self);self._create_holder.setVisible(False)
        ch=QVBoxLayout(self._create_holder);ch.setContentsMargins(0,0,0,0);ch.setSpacing(0)
        ch.addWidget(self.tab_create,1)
        self._create_dialog=None
        self.tabs.currentChanged.connect(self._on_tab)
        QShortcut(QKeySequence("Ctrl+Shift+C"),self,activated=lambda:self._add_command(False))
        QShortcut(QKeySequence("Ctrl+S"),self,activated=lambda:self._save_note(False))
        self._toast=QFrame(self);self._toast.setObjectName("Toast");self._toast.hide()
        th=QHBoxLayout(self._toast);th.setContentsMargins(14,10,14,10);th.setSpacing(10)
        self._toast_msg=QLabel("",self._toast);self._toast_msg.setObjectName("ToastMsg")
        th.addWidget(self._toast_msg,1)
        self._placeholder_timer=QTimer(self);self._placeholder_timer.setSingleShot(True)
        self._placeholder_timer.timeout.connect(self._update_placeholder_helper)
        _log("[+]",f"Note ready db={os.path.basename(self._dbp)}")
    def _build_create(self):
        v=QVBoxLayout(self.tab_create);v.setContentsMargins(0,0,0,0);v.setSpacing(6)
        top=QHBoxLayout();top.setContentsMargins(14,6,14,0);top.setSpacing(8)
        self.in_name=QLineEdit(self.tab_create);self.in_name.setObjectName("NoteName");self.in_name.setPlaceholderText("Note Name");self.in_name.setMaxLength(256)
        self.btn_add=QToolButton(self.tab_create);self.btn_add.setObjectName("NoteAddCmd");self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_add.setText("Add Command")
        self.btn_link=QToolButton(self.tab_create);self.btn_link.setObjectName("NoteAddLink");self.btn_link.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_link.setText("Add Link")
        self.btn_pick=QToolButton(self.tab_create);self.btn_pick.setObjectName("NotePickCmd");self.btn_pick.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_pick.setText("Pick Command")
        self.btn_clear=QToolButton(self.tab_create);self.btn_clear.setObjectName("NoteClear");self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_clear.setText("New Note")
        self.btn_save=QToolButton(self.tab_create);self.btn_save.setObjectName("NoteSave");self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_save.setText("Save")
        for b in (self.btn_add,self.btn_link,self.btn_pick,self.btn_clear,self.btn_save):
            f=b.font();f.setBold(True);f.setWeight(900);b.setFont(f)
        self.btn_add.clicked.connect(lambda:self._add_command(False))
        self.btn_link.clicked.connect(self._add_note_link)
        self.btn_pick.clicked.connect(self._open_cmd_picker)
        self.btn_clear.clicked.connect(self._clear_note)
        self.btn_save.clicked.connect(lambda:self._save_note(True))
        top.addWidget(self.in_name,1);top.addWidget(self.btn_add,0);top.addWidget(self.btn_link,0);top.addWidget(self.btn_pick,0);top.addWidget(self.btn_clear,0);top.addWidget(self.btn_save,0)
        bar=QFrame(self.tab_create);bar.setObjectName("NoteBar")
        bh=QHBoxLayout(bar);bh.setContentsMargins(14,6,14,6);bh.setSpacing(8)
        self.b_b=QToolButton(bar);self.b_b.setObjectName("FmtBold");self.b_b.setCursor(Qt.CursorShape.PointingHandCursor);self.b_b.setText("B");self.b_b.setCheckable(True)
        self.b_i=QToolButton(bar);self.b_i.setObjectName("FmtItalic");self.b_i.setCursor(Qt.CursorShape.PointingHandCursor);self.b_i.setText("I");self.b_i.setCheckable(True)
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
        self.btn_ref_color=QToolButton(bar);self.btn_ref_color.setObjectName("FmtRefColor");self.btn_ref_color.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_ref_color.setText("Ref Color")
        self.btn_ref_color.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        rm=QMenu(self.btn_ref_color)
        for name,hexv in (("Default",None),("Light Purple","#b197fc"),("Blue","#4dabf7"),("Green","#8ce99a"),("Yellow","#ffd43b"),("Orange","#ff922b"),("Red","#ff6b6b"),("White","#ffffff")):
            a=QAction(name,self.btn_ref_color);a.triggered.connect(lambda chk=False,v=hexv:self._set_note_ref_color(v));rm.addAction(a)
        self.btn_ref_color.setMenu(rm)
        self.align_left=QToolButton(bar);self.align_left.setObjectName("FmtAlignLeft");self.align_left.setCursor(Qt.CursorShape.PointingHandCursor)
        self.align_center=QToolButton(bar);self.align_center.setObjectName("FmtAlignCenter");self.align_center.setCursor(Qt.CursorShape.PointingHandCursor)
        il=_abs("..","Assets","left-align.png")
        if os.path.isfile(il):self.align_left.setIcon(QIcon(il));self.align_left.setIconSize(QSize(16,16))
        else:self.align_left.setText("Left")
        ic=_abs("..","Assets","center.png")
        if os.path.isfile(ic):self.align_center.setIcon(QIcon(ic));self.align_center.setIconSize(QSize(16,16))
        else:self.align_center.setText("Center")
        self.btn_img=QToolButton(bar);self.btn_img.setObjectName("FmtImage");self.btn_img.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_img.setText("Image")
        ii=_abs("..","Assets","image_icon.png")
        if os.path.isfile(ii):self.btn_img.setIcon(QIcon(ii));self.btn_img.setIconSize(QSize(16,16))
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
        self.btn_ref_color.setFixedHeight(30)
        bh.addWidget(self.b_b,0);bh.addWidget(self.b_i,0);bh.addWidget(self.b_u,0)
        bh.addSpacing(10)
        bh.addWidget(self.font_size,0);bh.addWidget(self.btn_color,0);bh.addWidget(self.btn_ref_color,0)
        bh.addSpacing(10)
        bh.addWidget(self.align_left,0);bh.addWidget(self.align_center,0)
        bh.addSpacing(10)
        bh.addWidget(self.btn_img,0);bh.addWidget(self.lst,0);bh.addWidget(self.tbl,0)
        bh.addStretch(1)
        self.cmd_box=QFrame(self.tab_create);self.cmd_box.setObjectName("CmdInlineBox");self.cmd_box.setVisible(False)
        cb=QVBoxLayout(self.cmd_box);cb.setContentsMargins(14,8,14,8);cb.setSpacing(8)
        g=QGridLayout();g.setContentsMargins(0,0,0,0);g.setHorizontalSpacing(8);g.setVerticalSpacing(8)
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
        b=QHBoxLayout();b.setContentsMargins(0,0,0,0);b.setSpacing(8)
        self.cmd_ins=QToolButton(self.cmd_box);self.cmd_ins.setObjectName("CmdBoxInsert");self.cmd_ins.setCursor(Qt.CursorShape.PointingHandCursor);self.cmd_ins.setText("Insert")
        self.cmd_can=QToolButton(self.cmd_box);self.cmd_can.setObjectName("CmdBoxCancel");self.cmd_can.setCursor(Qt.CursorShape.PointingHandCursor);self.cmd_can.setText("Cancel")
        for x in (self.cmd_ins,self.cmd_can):
            f=x.font();f.setBold(True);f.setWeight(900);x.setFont(f)
        self.cmd_ins.clicked.connect(self._cmd_box_insert)
        self.cmd_can.clicked.connect(self._cmd_box_hide)
        b.addStretch(1);b.addWidget(self.cmd_ins,0);b.addWidget(self.cmd_can,0);b.addStretch(1)
        cb.addLayout(b)
        self.edit=NoteEdit(self._add_command,self._heading_enter,self._on_cmd_anchor,self._is_cmd_table,self._on_note_ref,self._on_note_ref,self._edit_note_link_dialog,self.tab_create);self.edit.setPlaceholderText("Write your notes here...")
        self._note_ref_color=_note_ref_color()
        self._update_color_button(None)
        self._update_ref_color_button(self._note_ref_color)
        v.addLayout(top)
        v.addWidget(bar,0)
        v.addWidget(self.cmd_box,0)
        v.addWidget(self.edit,1)
        self.in_name.textChanged.connect(self._mark_dirty)
        self.edit.textChanged.connect(self._mark_dirty)
        self._placeholder_highlighter=_PlaceholderHighlighter(self.edit.document())
        try:self._placeholder_highlighter.set_note_ref_color(self._note_ref_color)
        except Exception:pass
        self._refresh_placeholder_keys(force=True)
        self._update_placeholder_helper()
    def _build_nav(self):
        v=QVBoxLayout(self.tab_nav);v.setContentsMargins(10,10,10,10);v.setSpacing(10)
        split=QSplitter(Qt.Orientation.Horizontal,self.tab_nav);split.setObjectName("NoteNavSplit")
        v.addWidget(split,1)
        left=QFrame(split);left.setObjectName("NoteNavLeft")
        lv=QVBoxLayout(left);lv.setContentsMargins(10,10,10,10);lv.setSpacing(8)
        self.nav_search=QLineEdit(left);self.nav_search.setObjectName("NoteAddSearch");self.nav_search.setPlaceholderText("Search notes...")
        self.nav_search.setMinimumHeight(30);self.nav_search.setMaximumHeight(30)
        self.nav_search.textChanged.connect(self._on_nav_search)
        lv.addWidget(self.nav_search,0)
        self.nav_sep=QFrame(left);self.nav_sep.setObjectName("NoteNavSep")
        self.nav_sep.setFixedHeight(2)
        self.nav_sep.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        lv.addWidget(self.nav_sep,0)
        self.nav_scroll=QScrollArea(left);self.nav_scroll.setObjectName("NoteNavScroll")
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav_list_frame=QFrame(self.nav_scroll);self.nav_list_frame.setObjectName("NoteNavList")
        self.nav_list_layout=QVBoxLayout(self.nav_list_frame);self.nav_list_layout.setContentsMargins(0,0,0,0);self.nav_list_layout.setSpacing(6)
        self.nav_scroll.setWidget(self.nav_list_frame)
        lv.addWidget(self.nav_scroll,1)
        right=QFrame(split);right.setObjectName("NoteNavDisplayFrame")
        rv=QVBoxLayout(right);rv.setContentsMargins(12,12,12,12);rv.setSpacing(8)
        self.nav_title=QLabel("Select a note",right);self.nav_title.setObjectName("NoteNavTitle")
        self.nav_view=QTextBrowser(right);self.nav_view.setObjectName("NoteNavDisplay")
        self.nav_view.setReadOnly(True)
        self.nav_view.setOpenExternalLinks(False)
        try:self.nav_view.setOpenLinks(False)
        except Exception:pass
        try:self.nav_view.anchorClicked.connect(self._nav_handle_anchor)
        except Exception:pass
        rv.addWidget(self.nav_title,0)
        rv.addWidget(self.nav_view,1)
        split.addWidget(left);split.addWidget(right)
        split.setStretchFactor(0,0);split.setStretchFactor(1,1)
        self._nav_group=QButtonGroup(self);self._nav_group.setExclusive(True)
        self._nav_selected=None
    def _nav_elide_text(self,text,width,font):
        try:
            fm=QFontMetrics(font)
            return fm.elidedText(text,Qt.TextElideMode.ElideRight,max(10,int(width)))
        except Exception:
            return text
    def resizeEvent(self,e):
        try:super().resizeEvent(e)
        except:pass
        try:self._toast_place()
        except:pass
        try:
            if self.tabs.currentIndex()==0:
                self._render_nav_list()
        except Exception:
            pass
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
        try:self._update_placeholder_helper()
        except Exception:pass
        try:self.in_name.setFocus()
        except:pass
    def _build_list(self):
        v=QVBoxLayout(self.tab_list);v.setContentsMargins(0,0,0,0);v.setSpacing(6)
        top=QHBoxLayout();top.setContentsMargins(14,8,14,8);top.setSpacing(10)
        self.btn_create=QToolButton(self.tab_list);self.btn_create.setObjectName("NoteCreateBtn");self.btn_create.setCursor(Qt.CursorShape.PointingHandCursor);self.btn_create.setText(" Create Note")
        self.btn_create.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        ico=_abs("..","Assets","add.png")
        if os.path.isfile(ico):self.btn_create.setIcon(QIcon(ico));self.btn_create.setIconSize(QSize(16,16))
        self.btn_create.setMinimumHeight(30);self.btn_create.setMaximumHeight(30)
        self.btn_create.clicked.connect(lambda:self._open_create_dialog(True))
        self.list_search=QLineEdit(self.tab_list);self.list_search.setObjectName("NoteAddSearch");self.list_search.setPlaceholderText("Search notes...")
        self.list_search.setMinimumHeight(30);self.list_search.setMaximumHeight(30)
        self.list_search.textChanged.connect(self._on_list_search)
        top.addWidget(self.btn_create,0)
        top.addWidget(self.list_search,1)
        self.quick_wrap=QFrame(self.tab_list);self.quick_wrap.setObjectName("NotesQuickFrame");self.quick_wrap.setVisible(False)
        qw=QHBoxLayout(self.quick_wrap);qw.setContentsMargins(10,0,10,0);qw.setSpacing(12)
        self.quick_pinned=QFrame(self.quick_wrap);self.quick_pinned.setObjectName("NotesPinnedRow")
        pb=QHBoxLayout(self.quick_pinned);pb.setContentsMargins(0,0,0,0);pb.setSpacing(6)
        self.quick_pinned_lbl=QLabel("Pinned:",self.quick_pinned);self.quick_pinned_lbl.setObjectName("NotesQuickLabel");self.quick_pinned_lbl.setVisible(False)
        self.quick_pinned_list=QFrame(self.quick_pinned);self.quick_pinned_list.setObjectName("NotesPinnedList")
        self.quick_pinned_row=QHBoxLayout(self.quick_pinned_list);self.quick_pinned_row.setContentsMargins(0,0,0,0);self.quick_pinned_row.setSpacing(6)
        pb.addWidget(self.quick_pinned_lbl,0);pb.addWidget(self.quick_pinned_list,1)
        qw.addWidget(self.quick_pinned,1)
        self.list_wrap=QFrame(self.tab_list);self.list_wrap.setObjectName("NoteAddTableFrame")
        tw=QVBoxLayout(self.list_wrap);tw.setContentsMargins(10,10,10,10);tw.setSpacing(10)
        self.list_tbl=QTableWidget(self.list_wrap);self.list_tbl.setObjectName("NoteAddTable")
        self.list_tbl.setColumnCount(5)
        self.list_tbl.setHorizontalHeaderLabels(["Pin","Note","Updated","#","X"])
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
        h.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.list_tbl.setColumnWidth(0,44);self.list_tbl.setColumnWidth(3,44);self.list_tbl.setColumnWidth(4,44)
        tw.addWidget(self.list_tbl,1)
        self.list_pager=QFrame(self.list_wrap);self.list_pager.setObjectName("NotesPagerFrame")
        ph=QHBoxLayout(self.list_pager);ph.setContentsMargins(0,0,0,0);ph.setSpacing(10)
        self.list_total=QLabel("",self.list_pager);self.list_total.setObjectName("NotesTotal")
        mid=QHBoxLayout();mid.setContentsMargins(0,0,0,0);mid.setSpacing(8)
        self.list_prev=QToolButton(self.list_pager);self.list_prev.setObjectName("NotesPagePrev");self.list_prev.setText("<");self.list_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_next=QToolButton(self.list_pager);self.list_next.setObjectName("NotesPageNext");self.list_next.setText(">");self.list_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_page=QLabel("0 of 0",self.list_pager);self.list_page.setObjectName("NotesPageLabel");self.list_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_prev.clicked.connect(self._list_prev_page);self.list_next.clicked.connect(self._list_next_page)
        mid.addWidget(self.list_prev,0);mid.addWidget(self.list_page,0);mid.addWidget(self.list_next,0)
        right=QHBoxLayout();right.setContentsMargins(0,0,0,0);right.setSpacing(8)
        self.list_per=QComboBox(self.list_pager);self.list_per.setObjectName("NotesPerPage")
        self.list_per.addItems(["10","20","50","100"]);self.list_per.setCurrentText("10")
        self.list_per.currentTextChanged.connect(self._on_list_per_page)
        self.list_per_lbl=QLabel("per page",self.list_pager);self.list_per_lbl.setObjectName("NotesPerPageLbl")
        right.addWidget(self.list_per,0);right.addWidget(self.list_per_lbl,0)
        ph.addWidget(self.list_total,0);ph.addStretch(1);ph.addLayout(mid,0);ph.addStretch(1);ph.addLayout(right,0)
        tw.addWidget(self.list_pager,0)
        v.addLayout(top)
        v.addWidget(self.quick_wrap,0)
        v.addWidget(self.list_wrap,1)
    def _on_nav_search(self,*a):
        self._render_nav_list()
    def _render_nav_list(self,force=False):
        if force or not self._notes_cache:
            try:self._notes_cache=_load_notes(self._dbp)
            except Exception:self._notes_cache=[]
        q=_norm(self.nav_search.text()).lower() if hasattr(self,"nav_search") else ""
        rows=[]
        for n in self._notes_cache:
            nm=_norm(n.get("note_name",""))
            if not nm:continue
            if q and q not in nm.lower():continue
            rows.append(n)
        try:self._clear_layout(self.nav_list_layout)
        except Exception:pass
        self._nav_group=QButtonGroup(self);self._nav_group.setExclusive(True)
        if not rows:
            lbl=QLabel("No notes",self.nav_list_frame);lbl.setObjectName("NoteNavEmpty")
            self.nav_list_layout.addWidget(lbl,0)
            self.nav_list_layout.addStretch(1)
            self.nav_title.setText("Select a note")
            self.nav_view.clear()
            return
        view_w=0
        try:
            view_w=self.nav_scroll.viewport().width()
        except Exception:
            view_w=0
        avail=max(120,(view_w-24) if view_w>0 else 220)
        for n in rows:
            nm=_norm(n.get("note_name",""))
            b=QToolButton(self.nav_list_frame);b.setObjectName("NoteNavBtn");b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setText(self._nav_elide_text(nm,avail,b.font()));b.setCheckable(True)
            b.setToolTip(nm)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(32);b.setMaximumHeight(32)
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos,btn=b,v=n:self._nav_show_menu(btn,pos,v))
            b.clicked.connect(lambda chk=False,v=n:self._nav_open_note(v))
            if self._nav_selected and _kci(self._nav_selected)==_kci(nm):
                b.setChecked(True)
            self._nav_group.addButton(b)
            self.nav_list_layout.addWidget(b,0)
        self.nav_list_layout.addStretch(1)
    def _nav_open_note(self,n):
        if not isinstance(n,dict):return
        nm=_norm(n.get("note_name",""))
        self._nav_selected=nm
        self.nav_title.setText(nm or "Note")
        try:self.nav_view.setHtml(n.get("content","") or "")
        except Exception:
            try:self.nav_view.setPlainText(_strip_html(n.get("content","") or ""))
            except Exception:pass
    def _nav_show_menu(self,btn,pos,n):
        if not isinstance(n,dict):return
        m=QMenu(btn)
        act=m.addAction("Edit Note")
        act.triggered.connect(lambda chk=False,v=n:self._nav_edit_note(v))
        m.exec(btn.mapToGlobal(pos))
    def _nav_edit_note(self,n):
        if not isinstance(n,dict):return
        if not self._confirm_save_if_dirty():return
        self._load_into_editor(n)
    def _nav_handle_anchor(self,url):
        try:
            href=str(url.toString())
        except Exception:
            href=str(url)
        if not href:return
        if href.startswith(_NOTE_LINK_ANCHOR):
            data=_decode_note_link_data(href[len(_NOTE_LINK_ANCHOR):])
            note=_norm(data.get("note",""))
            if note:self.open_note_by_name(note)
    def _open_note_in_nav(self,n):
        if not isinstance(n,dict):return False
        if not self._confirm_save_if_dirty():return False
        try:self.tabs.setCurrentIndex(0)
        except Exception:pass
        self._nav_open_note(n)
        try:self._render_nav_list()
        except Exception:pass
        return True
    def _attach_create_panel(self,layout):
        if layout is None:return
        try:
            p=self.tab_create.parent()
            if p and p.layout():p.layout().removeWidget(self.tab_create)
        except Exception:
            pass
        try:
            parent=None
            try:parent=layout.parentWidget()
            except Exception:parent=layout.parent()
            if isinstance(parent,QWidget):self.tab_create.setParent(parent)
            layout.addWidget(self.tab_create,1)
            self.tab_create.setVisible(True)
            try:layout.activate()
            except Exception:pass
            self.tab_create.show()
        except Exception:
            pass
    def _detach_create_panel(self):
        try:self._attach_create_panel(self._create_holder.layout())
        except Exception:pass
        try:self.tab_create.hide()
        except Exception:pass
    def _open_create_dialog(self,reset):
        if reset:
            if not self._confirm_save_if_dirty():return False
            self._new_note()
        if self._create_dialog and self._create_dialog.isVisible():
            try:self._create_dialog.raise_();self._create_dialog.activateWindow()
            except Exception:pass
            try:self.in_name.setFocus()
            except Exception:pass
            return True
        dlg=_CreateNoteDialog(self)
        self._create_dialog=dlg
        self._attach_create_panel(dlg.body_layout)
        try:dlg.show();dlg.raise_();dlg.activateWindow()
        except Exception:pass
        try:self.tab_create.setVisible(True);self.tab_create.raise_();self.tab_create.update()
        except Exception:pass
        try:self.in_name.setFocus()
        except Exception:pass
        return True
    def _on_create_dialog_closed(self):
        self._detach_create_panel()
        self._create_dialog=None
    def _on_tab(self,i):
        try:self._cmd_box_hide()
        except:pass
        if i==0:
            self._render_nav_list()
        elif i==1:
            self._render_list()
    def _mark_dirty(self,*a):
        self._dirty=True
        self._schedule_placeholder_scan()
    def _needs_save_prompt(self):
        if not self._dirty:
            return False
        try:
            name=_norm(self.in_name.text())
            body=_norm(self.edit.toPlainText())
            if not name and not body:
                self._dirty=False
                return False
            sig=_sig(name,self.edit.toHtml())
            if self._last_sig==sig:
                self._dirty=False
                return False
        except Exception:
            return True
        return True
    def _confirm_save_if_dirty(self):
        if not self._needs_save_prompt():
            return True
        w=self.window() if self.window() else self
        msg="Save changes to the current note before opening another?"
        btns=QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No|QMessageBox.StandardButton.Cancel
        res=QMessageBox.question(w,"Unsaved Note",msg,btns)
        if res==QMessageBox.StandardButton.Yes:
            return bool(self._save_note(False))
        if res==QMessageBox.StandardButton.No:
            return True
        return False
    def _schedule_placeholder_scan(self):
        if hasattr(self,"_placeholder_timer"):
            self._placeholder_timer.start(250)
    def _refresh_placeholder_keys(self,force=False):
        p=_targets_values_path()
        try:mt=os.path.getmtime(p)
        except Exception:mt=None
        if not force and self._targets_mtime==mt and self._placeholder_keys:return
        keys,_,_=_load_target_priorities()
        self._placeholder_keys={_kci(k) for k in keys.keys()}
        self._placeholder_key_list=sorted(keys.keys(),key=lambda s:s.lower())
        self._targets_mtime=mt
        try:self._placeholder_highlighter.set_known(self._placeholder_keys)
        except Exception:pass
    def _get_placeholder_key_list(self):
        try:self._refresh_placeholder_keys()
        except Exception:pass
        return list(self._placeholder_key_list or [])
    def _update_placeholder_helper(self):
        try:self._refresh_placeholder_keys()
        except Exception:pass
        if not hasattr(self,"placeholder_status"):
            return
        text=self.edit.toPlainText() if hasattr(self,"edit") else ""
        unknown=[];invalid=[]
        seen=set()
        for m in re.finditer(r"\{([^{}\r\n]+)\}",text or ""):
            raw=_norm(m.group(1))
            if not raw:continue
            lk=_kci(raw)
            if lk in seen:continue
            seen.add(lk)
            if not _is_valid_key(raw):
                invalid.append(raw)
                continue
            if lk not in self._placeholder_keys:
                unknown.append(raw)
        msg="Placeholders: ok"
        tip=""
        color="#8ce99a"
        if unknown or invalid:
            parts=[]
            if unknown:parts.append(f"Unknown {len(unknown)}")
            if invalid:parts.append(f"Invalid {len(invalid)}")
            msg="Placeholders: "+(" | ".join(parts))
            tip_parts=[]
            if unknown:tip_parts.append("Unknown: "+", ".join(unknown[:12]))
            if invalid:tip_parts.append("Invalid: "+", ".join(invalid[:12]))
            tip=" | ".join(tip_parts)
            color="#ffd43b" if unknown and not invalid else "#ff6b6b"
        try:
            self.placeholder_status.setText(msg)
            self.placeholder_status.setToolTip(tip)
            self.placeholder_status.setStyleSheet(f"color:{color};")
        except Exception:
            pass
    def _snip(self,s,n=90):
        t=_norm(s)
        return t if len(t)<=n else t[:max(0,n-3)]+"..."
    def _split_tags_text(self,t):
        raw=_norm(t)
        if not raw:return []
        parts=re.split(r"[;,]",raw)
        out=[];seen=set()
        for p in parts:
            k=_norm(p)
            if not k:continue
            lk=_kci(k)
            if lk in seen:continue
            seen.add(lk);out.append(k)
        return out
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
        self._current_font_size=size
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
    def _update_ref_color_button(self,hexv):
        color=_norm_hex_color(hexv) or _NOTE_REF_COLOR_DEFAULT
        h=color.lstrip("#")
        if len(h)!=6:
            self.btn_ref_color.setText("Ref Color")
            self.btn_ref_color.setStyleSheet("QToolButton#FmtRefColor{background:#ffffff;color:#000000;border:1px solid #2b2b2b;border-radius:8px;padding:2px 8px;}")
            return
        r=int(h[0:2],16);g=int(h[2:4],16);b=int(h[4:6],16)
        fg="#000000" if (r*0.299+g*0.587+b*0.114)>140 else "#ffffff"
        self.btn_ref_color.setText("Ref Color")
        self.btn_ref_color.setStyleSheet(f"QToolButton#FmtRefColor{{background:{color};color:{fg};border:1px solid #2b2b2b;border-radius:8px;padding:2px 8px;}}")
    def _set_note_ref_color(self,hexv):
        color=_norm_hex_color(hexv)
        _set_note_ref_color_setting(color)
        use=color or _NOTE_REF_COLOR_DEFAULT
        self._note_ref_color=use
        try:self._placeholder_highlighter.set_note_ref_color(use)
        except Exception:pass
        self._update_ref_color_button(use)
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
        cur.insertImage(fmt)
        try:
            bf=QTextBlockFormat();bf.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cur.mergeBlockFormat(bf)
        except Exception:
            pass
        self.edit.setTextCursor(cur);self._dirty=True
    def _clear_heading_format(self):
        fmt=QTextCharFormat();fmt.setFontPointSize(_DEFAULT_FONT_SIZE);fmt.setFontWeight(400);self._merge_blockfmt(fmt)
        self._current_font_size=_DEFAULT_FONT_SIZE
        try:
            self.font_size.blockSignals(True)
            self.font_size.setCurrentText(str(int(_DEFAULT_FONT_SIZE)))
            self.font_size.blockSignals(False)
        except:pass
    def _heading_enter(self):
        try:self._maybe_insert_hr()
        except Exception:pass
        try:
            size=getattr(self,"_current_font_size",_DEFAULT_FONT_SIZE)
            fmt=QTextCharFormat();fmt.setFontPointSize(float(size))
            self.edit.mergeCurrentCharFormat(fmt)
        except Exception:
            pass
    def _maybe_insert_hr(self):
        try:
            cur=self.edit.textCursor()
            block=cur.block()
            prev=block.previous()
            if not prev.isValid():return
            if prev.text().strip()!="---":return
            c=QTextCursor(prev)
            c.select(QTextCursor.SelectionType.BlockUnderCursor)
            c.removeSelectedText()
            c.insertHtml("<hr>")
            c.movePosition(QTextCursor.MoveOperation.NextBlock)
            self.edit.setTextCursor(c)
            self._dirty=True
        except Exception:
            pass
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
        last_pos=-1
        while True:
            pos=cur.position()
            if pos==last_pos:
                break
            last_pos=pos
            if cur.atEnd():
                break
            tb=cur.currentTable()
            if tb:
                tid=id(tb)
                if tid not in seen:
                    seen.add(tid);tables.append(tb)
                try:
                    next_pos=tb.lastCursorPosition().position()+1
                    if next_pos<=pos:
                        break
                    cur.setPosition(next_pos)
                except Exception:
                    if not cur.movePosition(QTextCursor.MoveOperation.NextBlock):
                        break
                continue
            if not cur.movePosition(QTextCursor.MoveOperation.NextBlock):
                break
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
    def _insert_cmd_table(self,data,cursor=None,ensure_blank=True):
        d=dict(data or {})
        if not d.get("command"):return None
        token=_encode_cmd_data(d)
        cur=cursor if cursor is not None else self.edit.textCursor()
        try:
            tb=cur.currentTable()
            if tb:
                cur=QTextCursor(self.edit.document())
                cur.setPosition(tb.lastCursorPosition().position()+1)
        except Exception:
            pass
        if ensure_blank:
            try:
                blk=cur.block()
                if blk.isValid():
                    try:cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                    except Exception:pass
                    cur.insertBlock()
            except Exception:
                pass
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
            doc=self.edit.document()
            start=table.firstCursorPosition().position()
            end=table.lastCursorPosition().position()
            if end<start:start,end=end,start
            cur=QTextCursor(doc)
            cur.setPosition(start)
            cur.setPosition(min(end+1,doc.characterCount()-1),QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
            cur.deleteChar()
            self.edit.setTextCursor(cur)
        except Exception:
            try:
                cur=table.firstCursorPosition()
                cur.select(QTextCursor.SelectionType.TableUnderCursor)
                cur.removeSelectedText()
                cur.deleteChar()
                self.edit.setTextCursor(cur)
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
            self._insert_cmd_table(data,cur,ensure_blank=False)
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
    def _on_note_ref(self,name):
        nm=_norm(name)
        if not nm:return False
        if not self._confirm_save_if_dirty():
            return False
        if self.open_note_by_name(nm):
            return True
        self._toast_show(f"Note not found: {nm}",2000)
        return False
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
    def _open_cmd_picker(self):
        try:self._cmd_box_hide()
        except Exception:pass
        dlg=_CmdPickerDlg(self,self._dbp)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        row=dlg.selected()
        if not isinstance(row,dict):return
        title=_norm(row.get("cmd_note_title","")) or _norm(row.get("note_name","")) or _norm(self.in_name.text())
        cat=_norm(row.get("category",""))
        sub=_norm(row.get("sub_category",""))
        desc=_norm(row.get("description",""))
        tags=_norm(row.get("tags",""))
        cmd=_norm(row.get("command",""))
        cmd=(row.get("command_plain") or row.get("command") or "").rstrip()
        if not cmd:return
        data=self._cmd_data(title,cat,sub,desc,tags,cmd)
        cur=self.edit.textCursor()
        self._insert_cmd_table(data,cur)
        self._dirty=True
        try:self.edit.setFocus()
        except:pass
    def _note_link_names(self):
        try:rows=_load_notes(self._dbp)
        except Exception:rows=[]
        return [_norm(n.get("note_name","")) for n in rows if _norm(n.get("note_name",""))]
    def _add_note_link(self):
        cur=self.edit.textCursor()
        sel=cur.selectedText().replace("\u2029","\n").strip()
        if "\n" in sel:sel=" ".join([s.strip() for s in sel.splitlines() if s.strip()])
        notes=self._note_link_names()
        dlg=_NoteLinkDlg(self,notes,sel,"",_NOTE_LINK_COLOR_DEFAULT)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        vals=dlg.vals()
        if not isinstance(vals,dict):return
        note=vals.get("note","");title=vals.get("title","");color=vals.get("color","")
        if self.edit.insert_note_link(note,title,color,cur):
            try:self.edit.setFocus()
            except Exception:pass
    def _edit_note_link_dialog(self,data):
        notes=self._note_link_names()
        title=(str(data.get("title","")) if isinstance(data,dict) else "").replace("\r","\n").replace("\n"," ").strip()
        note=_norm(data.get("note","")) if isinstance(data,dict) else ""
        color=data.get("color","") if isinstance(data,dict) else ""
        dlg=_NoteLinkDlg(self,notes,title,note,color)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return None
        return dlg.vals()
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
        self._open_create_dialog(False)
        self._schedule_placeholder_scan()
        _log("[*]",f"Loaded note: {name}")
    def _on_list_search(self,*a):
        self._list_page=1
        self._render_list()
    def _list_pages(self):
        n=len(self._list_view);per=max(1,int(self._list_per))
        return max(1,(n+per-1)//per)
    def _list_slice(self):
        per=max(1,int(self._list_per))
        a=(self._list_page-1)*per
        b=a+per
        return self._list_view[a:b]
    def _list_prev_page(self):
        if self._list_page>1:
            self._list_page-=1
            self._render_list()
    def _list_next_page(self):
        if self._list_page<self._list_pages():
            self._list_page+=1
            self._render_list()
    def _on_list_per_page(self,t):
        try:self._list_per=int(t)
        except Exception:self._list_per=10
        self._list_page=1
        self._render_list()
    def _save_notes_meta(self):
        try:_save_notes_meta(self._pinned,self._recent)
        except Exception:pass
    def _prune_meta(self,names_set):
        before_p=list(self._pinned)
        before_r=list(self._recent)
        self._pinned=[x for x in self._pinned if _kci(x) in names_set]
        self._recent=[x for x in self._recent if _kci(x) in names_set]
        if before_p!=self._pinned or before_r!=self._recent:self._save_notes_meta()
    def _clear_layout(self,lay):
        try:
            while lay.count():
                it=lay.takeAt(0)
                w=it.widget()
                if w is not None:w.setParent(None)
        except Exception:
            pass
    def _render_quick_notes(self):
        return
    def _touch_recent(self,name,refresh_list=True):
        return
    def _toggle_pin(self,name):
        nm=_norm(name)
        if not nm:return
        k=_kci(nm)
        if k in {_kci(x) for x in self._pinned}:
            self._pinned=[x for x in self._pinned if _kci(x)!=k]
        else:
            self._pinned.insert(0,nm)
        self._pinned=_dedupe_ci(self._pinned)
        self._save_notes_meta()
        self._render_quick_notes()
        self._render_list()
    def _rename_note_meta(self,old_name,new_name):
        o=_norm(old_name);n=_norm(new_name)
        if not o or not n or _kci(o)==_kci(n):return
        self._pinned=[n if _kci(x)==_kci(o) else x for x in self._pinned]
        self._recent=[n if _kci(x)==_kci(o) else x for x in self._recent]
        self._pinned=_dedupe_ci(self._pinned)
        self._recent=_dedupe_ci(self._recent)
        self._save_notes_meta()
        self._render_quick_notes()
    def _remove_note_meta(self,name):
        nm=_norm(name)
        if not nm:return
        self._pinned=[x for x in self._pinned if _kci(x)!=_kci(nm)]
        self._recent=[x for x in self._recent if _kci(x)!=_kci(nm)]
        self._save_notes_meta()
        self._render_quick_notes()
    def _render_list(self):
        try:self._notes_cache=_load_notes(self._dbp)
        except Exception:self._notes_cache=[]
        names_set={_kci(n.get("note_name","")) for n in self._notes_cache if _norm(n.get("note_name",""))}
        self._prune_meta(names_set)
        q=_norm(self.list_search.text()).lower()
        rows=[]
        for n in self._notes_cache:
            nm=(n.get("note_name","") or "");up=(n.get("updated_at","") or "")
            if q and q not in (nm+" "+up).lower():continue
            rows.append(n)
        pin_set={_kci(x) for x in self._pinned}
        pin_index={_kci(x):i for i,x in enumerate(self._pinned)}
        pinned=[];rest=[]
        for n in rows:
            nm=_kci(n.get("note_name",""))
            if nm in pin_set:pinned.append(n)
            else:rest.append(n)
        pinned.sort(key=lambda n:pin_index.get(_kci(n.get("note_name","")),9999))
        rows=pinned+rest
        self._list_view=rows
        tot=len(self._list_view);pg=self._list_pages()
        if self._list_page>pg:self._list_page=pg
        if self._list_page<1:self._list_page=1
        if hasattr(self,"list_total"):self.list_total.setText(f"Total: {tot}")
        if hasattr(self,"list_page"):self.list_page.setText(f"{self._list_page} of {pg}")
        rows=self._list_slice()
        self.list_tbl.setRowCount(len(rows))
        for r,n in enumerate(rows):
            note_name=(n.get("note_name","") or "").strip()
            is_pin=_kci(note_name) in pin_set
            pin=QTableWidgetItem("");pin.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);pin.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ico=_abs("..","Assets","Fav_selected.png" if is_pin else "Fav.png")
            if os.path.isfile(ico):pin.setIcon(QIcon(ico))
            else:pin.setText("P" if is_pin else "")
            pin.setToolTip("Pinned" if is_pin else "Pin")
            nm=QTableWidgetItem(note_name);nm.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);nm.setTextAlignment(Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
            fn=nm.font();fn.setBold(True);fn.setWeight(800);nm.setFont(fn);nm.setData(Qt.ItemDataRole.UserRole,n)
            up=QTableWidgetItem(_fmt_note_time(n.get("updated_at","")));up.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);up.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ed=QTableWidgetItem("#");ed.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);ed.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            xd=QTableWidgetItem("X");xd.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);xd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fe=ed.font();fe.setBold(True);fe.setWeight(800);ed.setFont(fe);xd.setFont(fe)
            self.list_tbl.setItem(r,0,pin);self.list_tbl.setItem(r,1,nm);self.list_tbl.setItem(r,2,up);self.list_tbl.setItem(r,3,ed);self.list_tbl.setItem(r,4,xd)
            self.list_tbl.setRowHeight(r,44)
        self.list_tbl.clearSelection()
        try:self._render_quick_notes()
        except Exception:pass
    def _row_note(self,row):
        it=self.list_tbl.item(row,1)
        if not it:return None
        d=it.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d,dict) else None
    def _on_list_cell(self,row,col):
        n=self._row_note(row)
        if not n:return
        if col==0:
            name=(n.get("note_name","") or "").strip()
            return self._toggle_pin(name)
        if col in (1,2,3):
            if not self._confirm_save_if_dirty():return
            return self._load_into_editor(n)
        if col==4:
            w=self.window() if self.window() else self
            name=(n.get("note_name","") or "").strip()
            if QMessageBox.question(w,"Delete",f"Delete note: {name}?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            ok=_delete_note(self._dbp,name)
            if ok:
                self._remove_note_meta(name)
                self._render_list()
                try:self._render_nav_list(force=True)
                except Exception:pass
                _log("[+]",f"Deleted note: {name}")
            else:QMessageBox.critical(w,"Error","Failed to delete note.")
    def _on_list_double(self,row,col):
        n=self._row_note(row)
        if n:
            if not self._confirm_save_if_dirty():return
            self._load_into_editor(n)
    def _save_note(self,reset_after):
        if self._saving:return False
        self._saving=True
        self.btn_save.setEnabled(False);self.btn_clear.setEnabled(False);self.btn_add.setEnabled(False)
        try:
            prev_name=_norm(self._orig_name)
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
            try:
                if prev_name and _kci(prev_name)!=_kci(name):self._rename_note_meta(prev_name,name)
            except Exception:
                pass
            try:
                added=_auto_add_target_values(dbp)
                if added:_log("[+]",f"Auto-added target elements: {added}")
            except Exception as e:
                _log("[!]",f"Auto-add target elements failed ({e})")
            try:
                self._refresh_placeholder_keys(force=True)
                self._update_placeholder_helper()
            except Exception:
                pass
            try:self.note_saved.emit()
            except:pass
            try:self._render_list()
            except:pass
            try:self._render_nav_list(force=True)
            except Exception:pass
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
        if not self._confirm_save_if_dirty():
            return False
        try:
            self._notes_cache=_load_notes(self._dbp)
        except Exception:
            self._notes_cache=[]
        for n in self._notes_cache:
            if _norm(n.get("note_name","")).lower()==nm.lower():
                try:
                    return self._open_note_in_nav(n)
                except Exception:
                    return False
        return False
    def open_note_by_id(self,nid):
        try:tid=int(nid)
        except Exception:return False
        if not self._confirm_save_if_dirty():
            return False
        try:
            self._notes_cache=_load_notes(self._dbp)
        except Exception:
            self._notes_cache=[]
        for n in self._notes_cache:
            try:
                if int(n.get("id"))==tid:
                    return self._open_note_in_nav(n)
            except Exception:
                continue
        return False
    def create_note_prefill(self,name="",content=""):
        if not self._confirm_save_if_dirty():
            return False
        self._new_note()
        self._open_create_dialog(False)
        nm=_norm(name)
        if nm:self.in_name.setText(nm)
        if content is not None:
            txt=str(content)
            if txt:
                try:self.edit.setPlainText(txt)
                except Exception:pass
        self._dirty=True
        return True
